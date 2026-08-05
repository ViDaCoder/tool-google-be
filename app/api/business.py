import random
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.business import Business
from app.models.proxy import Proxy
from app.schemas.business import BusinessParseRequest, BusinessResponse
from app.interface.scraper import BaseScraper
from app.interface.llm import BaseLLMClient
from app.services.auth import get_current_user, get_scraper, get_llm_client

router = APIRouter(prefix="/business", tags=["Business Scraper"])

@router.post("/parse", response_model=BusinessResponse, status_code=status.HTTP_200_OK)
async def parse_business(
    request_data: BusinessParseRequest,
    db: AsyncSession = Depends(get_db),
    scraper: BaseScraper = Depends(get_scraper),
    llm_client: BaseLLMClient = Depends(get_llm_client),
    current_user = Depends(get_current_user)
):
    """
    Cào thông tin từ Google Maps và phân tích chiến lược doanh nghiệp sử dụng Gemini AI.
    Có cơ chế lưu cache trong 24 giờ để tăng tốc độ phản hồi.
    """
    clean_url = request_data.url.strip()

    # 1. Kiểm tra cache trong Database (24h = 86400 giây)
    result = await db.execute(select(Business).where(Business.url == clean_url))
    business = result.scalars().first()

    if business:
        time_elapsed = (datetime.now() - business.updated_at).total_seconds()
        # Đảm bảo bản ghi đã được phân tích bằng AI (không bị null)
        if time_elapsed < 86400 and business.analysis_info and business.review_strategy:
            print(f"[Cache Hit] Returning cached business data for URL: {clean_url}")
            return business
        print(f"[Cache Expired/Incomplete] Recrawling/Reanalyzing URL: {clean_url}")

    # 2. Đọc cấu hình AI Analytics từ DB và tạo Gemini Client động
    from app.models.settings import SystemSetting
    from app.AI.gemini import GeminiClient
    from app.services.logs import log_system_activity
    
    await log_system_activity(
        db, 
        "Bắt đầu cào doanh nghiệp", 
        f"Người dùng {current_user.email} đang yêu cầu xử lý URL Google Maps: {clean_url}", 
        "info"
    )
    
    settings_res = await db.execute(select(SystemSetting))
    settings_records = settings_res.scalars().all()
    settings_dict = {r.key: r.value for r in settings_records}
    
    analytics_key = settings_dict.get("analytics_api_key") or None
    analytics_model = settings_dict.get("analytics_model_id") or None
    analytics_prompt = settings_dict.get("analytics_system_prompt") or None
    
    # Tạo thực thể GeminiClient động từ cấu hình
    try:
        llm_client = GeminiClient(api_key=analytics_key, model_id=analytics_model, system_prompt=analytics_prompt)
    except Exception as init_err:
        print(f"[Warning] Failed to init custom GeminiClient, falling back to default: {init_err}")
        # llm_client giữ nguyên giá trị inject từ Depends

    # 3. Lấy proxy ngẫu nhiên đang hoạt động từ Database
    proxy_result = await db.execute(select(Proxy).where(Proxy.status == "Hoạt động"))
    active_proxies = proxy_result.scalars().all()

    proxy_str = None
    if active_proxies:
        chosen_proxy = random.choice(active_proxies)
        if chosen_proxy.username and chosen_proxy.password:
            proxy_str = f"http://{chosen_proxy.username}:{chosen_proxy.password}@{chosen_proxy.ip}:{chosen_proxy.port}"
        else:
            proxy_str = f"http://{chosen_proxy.ip}:{chosen_proxy.port}"
        print(f"[Scraper] Using proxy: {chosen_proxy.ip}:{chosen_proxy.port}")
    else:
        print("[Scraper] No active proxies found in DB. Scraping directly via host IP.")


    # 3. Tiến hành cào dữ liệu qua Scraper
    data = None
    scraper_error = None
    try:
        data = await scraper.parse_url(clean_url, proxy_str)
        if data and data.get("name"):
            await log_system_activity(
                db, 
                "Cào doanh nghiệp thành công", 
                f"Đã cào trực tiếp thành công doanh nghiệp '{data['name']}' qua HTTP Request.", 
                "success"
            )
    except Exception as e:
        scraper_error = e
        print(f"[Scraper Error] Failed to crawl Google Maps: {e}. Will attempt AI resolution fallback.")

    # 4. Nếu cào thất bại/bị chặn, thử dùng AI để phân tích thông tin từ URL
    if not data or not data.get("name"):
        import re
        import urllib.parse
        import hashlib
        
        extracted_name = None
        coordinates = None
        try:
            # Trích xuất tên từ đường dẫn: /maps/place/Tên+Doanh+Nghiệp/
            match_name = re.search(r"/maps/place/([^/]+)", clean_url)
            if match_name:
                extracted_name = urllib.parse.unquote(match_name.group(1).replace("+", " "))
            
            # Trích xuất tọa độ: @21.0252197,105.8524458
            match_coords = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", clean_url)
            if match_coords:
                coordinates = f"{match_coords.group(1)}, {match_coords.group(2)}"
        except Exception:
            pass

        if extracted_name:
            try:
                resolved = await llm_client.resolve_business_details(extracted_name, coordinates)
                if resolved["name"] and resolved["address"]:
                    # Điền các trường id và place_id giống như scraper
                    place_id = "ChIJ" + hashlib.md5(clean_url.encode("utf-8")).hexdigest()[:16].upper()
                    biz_id = "biz_" + hashlib.md5(resolved["name"].encode("utf-8")).hexdigest()[:10]
                    data = {
                        "id": biz_id,
                        "place_id": place_id,
                        "url": clean_url,
                        "name": resolved["name"],
                        "category": resolved["category"],
                        "address": resolved["address"],
                        "rating_score": resolved["rating_score"],
                        "review_count": resolved["review_count"],
                        "raw_reviews_sample": resolved["raw_reviews_sample"]
                    }
                    await log_system_activity(
                        db, 
                        "Giải quyết địa điểm bằng AI", 
                        f"Playwright bị chặn. Đã tự động phân giải thông tin thật của doanh nghiệp '{resolved['name']}' thành công bằng Gemini AI.", 
                        "success"
                    )
            except Exception as ai_err:
                print(f"[AI Resolution Error] Gemini failed to resolve business: {ai_err}")

    # Nếu cả cào và AI đều thất bại, hoặc không có thông tin
    if not data or not data.get("name"):
        detail_msg = "Không thể cào dữ liệu từ đường dẫn Google Maps này. Vui lòng kiểm tra lại liên kết hoặc cấu hình proxy."
        if scraper_error:
            detail_msg = f"Cào dữ liệu từ Google Maps thất bại: {str(scraper_error)}"
            
        await log_system_activity(
            db, 
            "Cào doanh nghiệp thất bại", 
            f"Không thể cào hoặc phân giải thông tin từ URL: {clean_url}. Lỗi: {str(scraper_error)}", 
            "error"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail_msg
        )

    # 5. Sử dụng Gemini AI để phân tích chiến lược
    try:
        ai_analysis = await llm_client.analyze_business(
            name=data["name"],
            category=data["category"],
            address=data["address"],
            reviews=data["raw_reviews_sample"]
        )
        await log_system_activity(
            db, 
            "Phân tích doanh nghiệp bằng AI", 
            f"Gemini AI đã hoàn thành phân tích thế mạnh và lập chiến lược review cho '{data['name']}'. Model: {llm_client.model}", 
            "success"
        )
    except Exception as e:
        print(f"[Gemini Analysis Error] Failed to analyze business using Gemini: {e}")
        await log_system_activity(
            db, 
            "Phân tích doanh nghiệp thất bại", 
            f"Lỗi khi gọi Gemini AI để phân tích doanh nghiệp '{data['name']}': {str(e)}", 
            "error"
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Lỗi khi phân tích dữ liệu bằng Gemini AI: {str(e)}"
        )

    # 5. Lưu dữ liệu cào được và kết quả phân tích của AI vào Database
    if business:
        # Cập nhật bản ghi cũ
        business.name = data["name"]
        business.category = data["category"]
        business.address = data["address"]
        business.rating_score = data["rating_score"]
        business.review_count = data["review_count"]
        business.raw_reviews_sample = data["raw_reviews_sample"]
        business.extracted_keywords = ai_analysis["extracted_keywords"]
        business.analysis_info = ai_analysis["analysis_info"]
        business.review_strategy = ai_analysis["review_strategy"]
        business.updated_at = datetime.now()
    else:
        # Tạo bản ghi mới
        business = Business(
            id=data["id"],
            place_id=data["place_id"],
            url=clean_url,
            name=data["name"],
            category=data["category"],
            address=data["address"],
            rating_score=data["rating_score"],
            review_count=data["review_count"],
            raw_reviews_sample=data["raw_reviews_sample"],
            extracted_keywords=ai_analysis["extracted_keywords"],
            analysis_info=ai_analysis["analysis_info"],
            review_strategy=ai_analysis["review_strategy"]
        )
        db.add(business)

    try:
        await db.commit()
        await db.refresh(business)
    except Exception as e:
        await db.rollback()
    return business


@router.get("", response_model=list[BusinessResponse], status_code=status.HTTP_200_OK)
async def get_businesses(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Lấy danh sách tất cả các doanh nghiệp đã lưu trong Database, sắp xếp theo thời gian mới nhất.
    """
    result = await db.execute(select(Business).order_by(Business.updated_at.desc()))
    businesses = result.scalars().all()
    return businesses


@router.delete("/{business_id}", status_code=status.HTTP_200_OK)
async def delete_business(
    business_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Xóa một bản ghi doanh nghiệp khỏi Database theo ID.
    """
    result = await db.execute(select(Business).where(Business.id == business_id))
    business = result.scalars().first()

    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy doanh nghiệp cần xóa."
        )

    try:
        await db.delete(business)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xóa doanh nghiệp từ cơ sở dữ liệu: {str(e)}"
        )

    return {"message": "Đã xóa doanh nghiệp thành công."}
