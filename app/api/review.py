import os
import shutil
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.models.business import Business
from app.models.history import ReviewHistory
from app.models.draft import ReviewDraft
from app.schemas.review import ReviewGenerateRequest, ReviewHistoryResponse
from app.interface.llm import BaseLLMClient
from app.services.auth import get_current_user, get_llm_client
from app.services.logs import log_system_activity

from app.models.gmail import GmailAccount
from app.models.gmail_proxy import GmailProxy

router = APIRouter(prefix="/reviews", tags=["Review Generator"])

class PostSuccessRequest(BaseModel):
    business_id: str
    gmail: str
    proxy: str
    rating: int = 5
    review_text: str
    images: list[str] = []

@router.post("/upload-image", status_code=status.HTTP_201_CREATED)
async def upload_review_image(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user)
):
    """
    Tải ảnh thực tế đăng kèm bài review lên server.
    """
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type and file.content_type.lower() not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Định dạng file không hỗ trợ. Chỉ chấp nhận JPG, PNG, WEBP."
        )

    upload_dir = os.path.join("uploads", "reviews")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    filename = f"img_{uuid.uuid4().hex[:12]}{ext}"
    file_path = os.path.join(upload_dir, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    abs_path = os.path.abspath(file_path)
    url_path = f"/uploads/reviews/{filename}"

    return {
        "url": url_path,
        "local_path": abs_path,
        "filename": filename
    }

@router.post("/generate", response_model=ReviewHistoryResponse, status_code=status.HTTP_201_CREATED)
async def generate_reviews(
    request_data: ReviewGenerateRequest,
    db: AsyncSession = Depends(get_db),
    llm_client: BaseLLMClient = Depends(get_llm_client),
    current_user = Depends(get_current_user)
):
    """
    Sinh danh sách review bằng AI (Gemini) dựa theo thông tin doanh nghiệp.
    Tự động kiểm tra và chỉ sinh số bài tối đa bằng đúng số Gmail chưa đánh giá địa điểm này.
    """
    # 1. Truy vấn thông tin doanh nghiệp từ database
    result = await db.execute(select(Business).where(Business.id == request_data.business_id))
    business = result.scalars().first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin doanh nghiệp trong hệ thống."
        )

    # 1b. Lọc danh sách Gmail khả dụng chưa đánh giá doanh nghiệp này
    gmail_res = await db.execute(select(GmailAccount).where(GmailAccount.status == "Hoạt động"))
    active_gmails = gmail_res.scalars().all()
    
    if not active_gmails:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hệ thống hiện chưa có tài khoản Gmail nào ở trạng thái Hoạt động. Vui lòng kiểm tra mục Quản lý Gmail."
        )

    # Lấy danh sách các Gmail ĐÃ ĐÁNH GIÁ hoặc ĐÃ CÓ BÀI NHÁP cho doanh nghiệp này
    hist_res = await db.execute(
        select(ReviewHistory).where(
            (ReviewHistory.business_id == business.id) | (ReviewHistory.business_name == business.name)
        )
    )
    history_records = hist_res.scalars().all()

    draft_res = await db.execute(
        select(ReviewDraft).where(
            (ReviewDraft.business_id == business.id) | (ReviewDraft.business_name == business.name)
        )
    )
    draft_records = draft_res.scalars().all()
    
    posted_gmails_set = set()
    for h in history_records:
        if isinstance(h.reviews, list):
            for r in h.reviews:
                if isinstance(r, dict) and r.get("gmail"):
                    posted_gmails_set.add(r["gmail"].strip().lower())

    for d in draft_records:
        if isinstance(d.reviews, list):
            for r in d.reviews:
                if isinstance(r, dict) and r.get("gmail"):
                    posted_gmails_set.add(r["gmail"].strip().lower())

    fresh_gmails = [g for g in active_gmails if g.email.strip().lower() not in posted_gmails_set]
    available_count = len(fresh_gmails)

    if available_count <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Doanh nghiệp '{business.name}' đã được tất cả {len(active_gmails)} tài khoản Gmail khả dụng (đã đăng hoặc đang có bài nháp) trong hệ thống sử dụng. Vui lòng xóa bài nháp cũ hoặc thêm Gmail mới!"
        )

    # Tự động giới hạn số lượng sinh tối đa bằng số Gmail khả dụng
    target_quantity = min(request_data.quantity, available_count)

    # 2. Đọc cấu hình AI Review từ DB và tạo Gemini Client động
    from app.models.settings import SystemSetting
    from app.AI.gemini import GeminiClient
    
    settings_res = await db.execute(select(SystemSetting))
    settings_records = settings_res.scalars().all()
    settings_dict = {r.key: r.value for r in settings_records}
    
    review_key = settings_dict.get("review_api_key") or None
    review_model = settings_dict.get("review_model_id") or None
    review_prompt = settings_dict.get("review_system_prompt") or None
    
    try:
        llm_client = GeminiClient(api_key=review_key, model_id=review_model, system_prompt=review_prompt)
    except Exception as init_err:
        print(f"[Warning] Failed to init custom GeminiClient, falling back to default: {init_err}")

    # 3. Gọi Gemini AI để sinh review theo yêu cầu
    try:
        business_details = {
            "name": business.name,
            "category": business.category,
            "address": business.address,
            "review_strategy": business.review_strategy
        }
        
        reviews = await llm_client.generate_reviews(
            business_details=business_details,
            tone=request_data.tone,
            language=request_data.language,
            length=request_data.length,
            quantity=target_quantity,
            focus_keywords=request_data.focus_keywords
        )

        # Lấy bảng ánh xạ Gmail -> Proxy bằng get_proxy_config_for_gmail
        from app.services.proxy_utils import get_proxy_config_for_gmail
        proxy_map = {}
        for g in fresh_gmails:
            p_config = await get_proxy_config_for_gmail(db, g.email)
            if p_config:
                server_clean = p_config["server"].replace("http://", "").replace("https://", "")
                if "username" in p_config and "password" in p_config:
                    proxy_map[g.email.lower()] = f"{server_clean}:{p_config['username']}:{p_config['password']}"
                else:
                    proxy_map[g.email.lower()] = server_clean

        # Tự động phân bổ hình ảnh cho từng bài review nháp mới
        try:
            import os
            import glob
            import random
            from app.services.poster import to_unsigned_snake_case
            
            used_images = set()
            
            # 1. Thu thập ảnh đã có trong Lịch sử Đăng bài (ReviewHistory)
            hist_res = await db.execute(
                select(ReviewHistory).where(ReviewHistory.business_id == business.id)
            )
            history_records = hist_res.scalars().all()
            for hr in history_records:
                if isinstance(hr.reviews, list):
                    for r_item in hr.reviews:
                        if isinstance(r_item, dict) and r_item.get("images"):
                            for img in r_item["images"]:
                                used_images.add(os.path.abspath(img).lower())
            
            # 2. Thu thập ảnh đã có trong các bài Nháp hiện có (ReviewDraft)
            draft_res = await db.execute(
                select(ReviewDraft).where(ReviewDraft.business_id == business.id)
            )
            draft_record = draft_res.scalars().first()
            if draft_record and isinstance(draft_record.reviews, list):
                for r_item in draft_record.reviews:
                    if isinstance(r_item, dict) and r_item.get("images"):
                        for img in r_item["images"]:
                            used_images.add(os.path.abspath(img).lower())
            
            # 3. Quét thư mục ảnh từ CSDL
            all_available_images = []
            setting_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "image_folder_path"))
            setting_rec = setting_res.scalars().first()
            hinh_google_root = (setting_rec.value if setting_rec and setting_rec.value else r"C:\hinh_google").strip()
            if os.path.exists(hinh_google_root):
                clean_snake_name = to_unsigned_snake_case(business.name)
                biz_dir_snake = os.path.join(hinh_google_root, clean_snake_name)
                clean_biz_name = re.sub(r'[\\/*?:"<>|]', '', business.name).strip()
                biz_dir = os.path.join(hinh_google_root, clean_biz_name)
                biz_dir_raw = os.path.join(hinh_google_root, business.name.strip())
                
                target_dir = None
                if os.path.exists(biz_dir_snake) and os.path.isdir(biz_dir_snake):
                    target_dir = biz_dir_snake
                elif os.path.exists(biz_dir) and os.path.isdir(biz_dir):
                    target_dir = biz_dir
                elif os.path.exists(biz_dir_raw) and os.path.isdir(biz_dir_raw):
                    target_dir = biz_dir_raw
                
                if target_dir:
                    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"):
                        all_available_images.extend(glob.glob(os.path.join(target_dir, ext)))
                        all_available_images.extend(glob.glob(os.path.join(target_dir, ext.upper())))
                else:
                    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"):
                        all_available_images.extend(glob.glob(os.path.join(hinh_google_root, ext)))
                        all_available_images.extend(glob.glob(os.path.join(hinh_google_root, ext.upper())))
            
            all_available_images = list(set([os.path.abspath(p) for p in all_available_images]))
            unselected_images = [p for p in all_available_images if p.lower() not in used_images]
            
            print(f"[Generate API Allocation] Total available: {len(all_available_images)}, Unselected: {len(unselected_images)}")
            
            # Phân bổ cho từng bài review
            for r in reviews:
                r["images"] = []
                if unselected_images:
                    num_to_select = min(random.randint(1, 4), len(unselected_images))
                    selected_for_r = random.sample(unselected_images, num_to_select)
                    r["images"] = selected_for_r
                    # Đánh dấu là đã sử dụng để không phân bổ lại
                    for img in selected_for_r:
                        used_images.add(img.lower())
                        unselected_images.remove(img)
                    print(f"[Generate API Allocation] Allocated {num_to_select} images to review: {selected_for_r}")
        except Exception as gen_alloc_err:
            print(f"[Generate API Allocation Error] Failed to pre-allocate images: {gen_alloc_err}")

        # Gán trực tiếp từng Gmail khả dụng chưa dùng cho bài nháp tương ứng
        # Đồng thời tự động đặt lịch đăng bài nếu auto_schedule = True
        import uuid
        import random
        from datetime import timedelta
        from app.models.schedule import ReviewSchedule
        
        do_schedule = request_data.auto_schedule
        start_at = request_data.schedule_start_at
        if do_schedule and start_at:
            if start_at.tzinfo is not None:
                start_at = start_at.astimezone().replace(tzinfo=None)
            start_at = start_at.replace(second=0, microsecond=0)
            if start_at <= datetime.now():
                start_at = datetime.now() + timedelta(minutes=5)
                start_at = start_at.replace(second=0, microsecond=0)
        
        # Lấy toàn bộ các mốc thời gian đang chờ (pending) trong hệ thống để tránh trùng lặp
        sched_times_res = await db.execute(
            select(ReviewSchedule.scheduled_at).where(ReviewSchedule.status == "pending")
        )
        booked_times = [row[0] for row in sched_times_res.all()]

        current_scheduled_time = start_at
        
        for idx, r in enumerate(reviews):
            if idx < len(fresh_gmails):
                assigned_gmail = fresh_gmails[idx].email
                r["gmail"] = assigned_gmail
                r["proxy"] = proxy_map.get(assigned_gmail.lower(), "IP Máy chủ (Direct)")
                
                if do_schedule and start_at:
                    if idx > 0:
                        random_hours = random.uniform(request_data.min_interval_hours, request_data.max_interval_hours)
                        current_scheduled_time = current_scheduled_time + timedelta(hours=random_hours)
                        current_scheduled_time = current_scheduled_time.replace(second=0, microsecond=0)
                    
                    # Đảm bảo không trùng lặp / quá sát (Collision Avoidance) và nằm trong dải 9h - 22h
                    temp_time = current_scheduled_time.replace(second=0, microsecond=0)
                    if temp_time.hour < 9:
                        temp_time = temp_time.replace(hour=9, minute=random.randint(0, 30))
                    elif temp_time.hour > 22 or (temp_time.hour == 22 and temp_time.minute > 0):
                        temp_time = (temp_time + timedelta(days=1)).replace(hour=9, minute=random.randint(0, 30))
                    while True:
                        conflict = False
                        for booked_time in booked_times:
                            diff = abs((temp_time - booked_time.replace(second=0, microsecond=0)).total_seconds())
                            if diff < 300:  # Khoảng cách tối thiểu 5 phút
                                conflict = True
                                break
                        if conflict:
                            temp_time = temp_time + timedelta(minutes=random.randint(5, 15))
                        else:
                            current_scheduled_time = temp_time
                            booked_times.append(current_scheduled_time)
                            break
                    
                    schedule_id = f"sched_{uuid.uuid4().hex[:16]}"
                    new_schedule = ReviewSchedule(
                        id=schedule_id,
                        business_id=business.id,
                        gmail=assigned_gmail,
                        proxy=r["proxy"],
                        rating=r.get("rating", 5),
                        review_text=r.get("content", ""),
                        images=r.get("images", []),
                        scheduled_at=current_scheduled_time,
                        auto_submit=request_data.schedule_auto_submit,
                        headless=request_data.schedule_headless,
                        status="pending",
                        status_text=None,
                        user_email=current_user.email,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(new_schedule)
                    
                    r["status"] = "scheduled"
                    r["statusText"] = current_scheduled_time.strftime('%d/%m/%Y %H:%M')
                    r["scheduleId"] = schedule_id
                else:
                    r["status"] = "ready"
        
        await log_system_activity(
            db,
            "Sinh review thành công",
            f"Người dùng {current_user.email} sinh {target_quantity} review cho '{business.name}' (Khả dụng: {available_count}/{len(active_gmails)} Gmail). Model: {llm_client.model}",
            "success"
        )
    except Exception as e:
        print(f"[Generate Reviews Error] Failed to generate reviews via Gemini: {e}")
        await log_system_activity(
            db,
            "Sinh review thất bại",
            f"Lỗi khi sinh review cho doanh nghiệp '{business.name}': {str(e)}",
            "error"
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Lỗi khi gọi Gemini AI để sinh bài review: {str(e)}"
        )

    # 4. Lưu bài nháp review vào bảng review_drafts (Nối tiếp các bài mới vào bài nháp hiện có của doanh nghiệp)
    existing_draft_res = await db.execute(
        select(ReviewDraft).where(ReviewDraft.business_id == business.id)
    )
    existing_draft = existing_draft_res.scalars().first()

    if existing_draft:
        existing_reviews = existing_draft.reviews if isinstance(existing_draft.reviews, list) else []
        combined_reviews = existing_reviews + reviews
        existing_draft.reviews = combined_reviews
        existing_draft.created_at = datetime.now()
        draft_record = existing_draft
    else:
        draft_id = f"draft_{uuid.uuid4().hex[:16]}"
        draft_record = ReviewDraft(
            id=draft_id,
            business_id=business.id,
            business_name=business.name,
            category=business.category,
            url=business.url,
            tone=request_data.tone,
            language=request_data.language,
            length=request_data.length,
            custom_keywords=request_data.focus_keywords,
            reviews=reviews,
            created_at=datetime.now()
        )
        db.add(draft_record)

    await db.commit()
    
    return ReviewHistoryResponse(
        id=draft_record.id,
        business_id=business.id,
        business_name=business.name,
        category=business.category,
        url=business.url,
        tone=request_data.tone,
        language=request_data.language,
        length=request_data.length,
        custom_keywords=request_data.focus_keywords,
        reviews=draft_record.reviews,
        created_at=draft_record.created_at
    )


import re

def slugify(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text

async def _find_business_by_any_id(db: AsyncSession, business_id: str) -> Business | None:
    biz_res = await db.execute(select(Business))
    all_biz = biz_res.scalars().all()
    clean_id = business_id.strip().lower()
    for b in all_biz:
        if (
            b.id.lower() == clean_id or 
            b.name.strip().lower() == clean_id or 
            slugify(b.name) == clean_id
        ):
            return b
    return None


class DraftItemSchema(BaseModel):
    id: int | str | None = None
    rating: int = 5
    content: str
    images: list[str] = []
    gmail: str | None = None
    proxy: str | None = None
    status: str | None = None
    statusText: str | None = None

class UpdateDraftsRequest(BaseModel):
    reviews: list[DraftItemSchema]


@router.get("/drafts/{business_id}", status_code=status.HTTP_200_OK)
async def get_business_drafts(
    business_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Lấy danh sách các bài review nháp đã được sinh cho doanh nghiệp từ bảng review_drafts.
    """
    matched_biz = await _find_business_by_any_id(db, business_id)
    target_ids = {business_id.lower()}
    target_names = {business_id.lower()}
    if matched_biz:
        target_ids.add(matched_biz.id.lower())
        target_names.add(matched_biz.name.strip().lower())

    result = await db.execute(select(ReviewDraft).order_by(ReviewDraft.created_at.desc()))
    all_drafts = result.scalars().all()
    drafts = [
        d for d in all_drafts 
        if d.business_id.lower() in target_ids or d.business_name.strip().lower() in target_names
    ]
    
    all_reviews = []
    if drafts:
        latest_draft = drafts[0]
        if isinstance(latest_draft.reviews, list):
            all_reviews = latest_draft.reviews

            # Tự động phân bổ tăng cường thêm hình ảnh mới nếu có hình mới xuất hiện trong thư mục
            if matched_biz:
                try:
                    import os
                    import glob
                    import re
                    import random
                    from sqlalchemy.orm.attributes import flag_modified
                    from app.models.history import ReviewHistory
                    from app.services.gmail_proxy_service import get_gmail_proxy_map

                    # Lấy bảng ánh xạ Proxy mới nhất cho các Gmail trong hệ thống
                    gmail_proxy_map = await get_gmail_proxy_map(db)

                    # 1. Thu thập tất cả ảnh đã được dùng trước đó trong Lịch sử Đăng bài (ReviewHistory)
                    # Đồng thời lưu danh sách Content đã đăng để kiểm tra bài ĐÃ ĐĂNG
                    used_images = set()
                    posted_contents_set = set()
                    posted_images_map = {}
                    posted_content_gmail_map = {}

                    hist_res = await db.execute(
                        select(ReviewHistory).where(ReviewHistory.business_id == matched_biz.id)
                    )
                    history_records = hist_res.scalars().all()
                    for hr in history_records:
                        if isinstance(hr.reviews, list):
                            for r_item in hr.reviews:
                                if isinstance(r_item, dict):
                                    g_email = (r_item.get("gmail") or "").strip()
                                    r_cont = (r_item.get("content") or "").strip()
                                    if r_cont:
                                        posted_contents_set.add(r_cont)
                                        if g_email:
                                            posted_content_gmail_map[r_cont] = g_email
                                    if r_item.get("images"):
                                        p_imgs = [os.path.abspath(img).lower() for img in r_item["images"]]
                                        for img in r_item["images"]:
                                            used_images.add(os.path.abspath(img).lower())
                                        if g_email:
                                            posted_images_map[g_email.lower()] = set(p_imgs)

                    # 2. Thu thập ảnh trong các bài nháp review CHƯA ĐĂNG
                    # Đồng thời tự động cập nhật Proxy mới cho bài CHƯA ĐĂNG & dọn dẹp ảnh bị gán nhầm vào bài ĐÃ ĐĂNG
                    has_changed = False
                    for r in all_reviews:
                        if not isinstance(r, dict):
                            continue

                        r_gmail = (r.get("gmail") or "").strip().lower()
                        r_content = (r.get("content") or "").strip()
                        r_status = (r.get("status") or "")
                        is_posted = (
                            r_status == "success" or
                            r.get("posted") is True or
                            (r_content and r_content in posted_contents_set)
                        )

                        if is_posted:
                            # Khôi phục đúng Gmail đã dùng trong lịch sử đăng thực tế
                            actual_g = posted_content_gmail_map.get(r_content)
                            if actual_g and r.get("gmail") != actual_g:
                                r["gmail"] = actual_g
                                has_changed = True
                                r_gmail = actual_g.lower()

                            # Nếu bài đã đăng bị gán nhầm ảnh không có trong lịch sử đăng thực tế -> khôi phục lại
                            if "images" in r and r["images"]:
                                orig_images = posted_images_map.get(r_gmail, set())
                                cleaned_images = [img for img in r["images"] if os.path.abspath(img).lower() in orig_images]
                                if len(cleaned_images) != len(r["images"]):
                                    r["images"] = cleaned_images
                                    has_changed = True
                            for img in r.get("images", []):
                                used_images.add(os.path.abspath(img).lower())
                        else:
                            # Với bài CHƯA ĐĂNG: tự động đồng bộ Proxy mới nhất của Gmail nếu Proxy cũ đã hỏng/xóa/thay đổi
                            if r_gmail:
                                latest_proxy = gmail_proxy_map.get(r_gmail, "IP Máy chủ (Direct)") or "IP Máy chủ (Direct)"
                                if r.get("proxy") != latest_proxy:
                                    r["proxy"] = latest_proxy
                                    has_changed = True

                            if r.get("images"):
                                existing_imgs = [img for img in r["images"] if os.path.exists(img)]
                                if len(existing_imgs) != len(r["images"]):
                                    r["images"] = existing_imgs
                                    has_changed = True
                                for img in r.get("images", []):
                                    used_images.add(os.path.abspath(img).lower())

                    # 3. Quét thư mục ảnh của doanh nghiệp (đọc động từ CSDL)
                    all_available_images = []
                    from app.models.settings import SystemSetting
                    setting_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "image_folder_path"))
                    setting_rec = setting_res.scalars().first()
                    hinh_google_root = (setting_rec.value if setting_rec and setting_rec.value else r"C:\hinh_google").strip()

                    if os.path.exists(hinh_google_root):
                        from app.services.poster import to_unsigned_snake_case
                        clean_snake_name = to_unsigned_snake_case(matched_biz.name)
                        biz_dir_snake = os.path.join(hinh_google_root, clean_snake_name)
                        clean_biz_name = re.sub(r'[\\/*?:"<>|]', '', matched_biz.name).strip()
                        biz_dir = os.path.join(hinh_google_root, clean_biz_name)
                        biz_dir_raw = os.path.join(hinh_google_root, matched_biz.name.strip())

                        target_dir = None
                        if os.path.exists(biz_dir_snake) and os.path.isdir(biz_dir_snake):
                            target_dir = biz_dir_snake
                        elif os.path.exists(biz_dir) and os.path.isdir(biz_dir):
                            target_dir = biz_dir
                        elif os.path.exists(biz_dir_raw) and os.path.isdir(biz_dir_raw):
                            target_dir = biz_dir_raw

                        if target_dir:
                            for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"):
                                all_available_images.extend(glob.glob(os.path.join(target_dir, ext)))
                                all_available_images.extend(glob.glob(os.path.join(target_dir, ext.upper())))

                    all_available_images = list(set([os.path.abspath(p) for p in all_available_images]))
                    new_unused_images = [p for p in all_available_images if p.lower() not in used_images]

                    if new_unused_images:
                        print(f"[Sync API Allocation] Found {len(new_unused_images)} new unused images. Distributing ONLY to UNPOSTED drafts...")

                        # Phân bổ tăng cường CHỈ vào các bài nháp CHƯA ĐĂNG
                        for r in all_reviews:
                            if not isinstance(r, dict):
                                continue

                            r_content = (r.get("content") or "").strip()
                            r_status = (r.get("status") or "")
                            is_posted = (
                                r_status == "success" or
                                r.get("posted") is True or
                                (r_content and r_content in posted_contents_set)
                            )

                            # Bỏ qua tuyệt đối tất cả bài ĐÃ ĐĂNG
                            if is_posted:
                                continue

                            if "images" not in r:
                                r["images"] = []

                            current_images = r["images"]
                            current_count = len(current_images)

                            if current_count < 4 and new_unused_images:
                                max_add = 4 - current_count
                                num_to_add = min(random.randint(1, max_add), len(new_unused_images))
                                selected_new_imgs = random.sample(new_unused_images, num_to_add)

                                r["images"] = current_images + selected_new_imgs
                                has_changed = True

                                # Đánh dấu đã sử dụng
                                for img in selected_new_imgs:
                                    new_unused_images.remove(img)

                            if not new_unused_images:
                                break

                    if has_changed:
                        latest_draft.reviews = all_reviews
                        flag_modified(latest_draft, "reviews")
                        await db.commit()
                        print("[Sync API Allocation] Successfully updated images for UNPOSTED reviews and saved to DB.")
                except Exception as sync_alloc_err:
                    print(f"[Sync API Allocation Error] Failed to sync and allocate new images: {sync_alloc_err}")

        # Tự động dọn dẹp các bản ghi nháp rác dư thừa nếu có
        if len(drafts) > 1:
            for old_d in drafts[1:]:
                await db.delete(old_d)
            await db.commit()

    return {
        "business_id": business_id,
        "drafts": drafts[:1],
        "reviews": all_reviews
    }


@router.put("/drafts/{business_id}", status_code=status.HTTP_200_OK)
async def update_business_drafts(
    business_id: str,
    payload: UpdateDraftsRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Cập nhật danh sách bài nháp review của doanh nghiệp vào cơ sở dữ liệu (bảng review_drafts).
    """
    matched_biz = await _find_business_by_any_id(db, business_id)
    target_id = matched_biz.id if matched_biz else business_id
    target_name = matched_biz.name if matched_biz else business_id

    target_ids = {business_id.lower(), target_id.lower()}
    target_names = {business_id.lower(), target_name.strip().lower()}

    result = await db.execute(select(ReviewDraft).order_by(ReviewDraft.created_at.desc()))
    all_drafts = result.scalars().all()
    drafts = [
        d for d in all_drafts 
        if d.business_id.lower() in target_ids or d.business_name.strip().lower() in target_names
    ]

    formatted_reviews = [r.model_dump() for r in payload.reviews]

    if drafts:
        draft_record = drafts[0]
        draft_record.business_id = target_id
        draft_record.business_name = target_name
        draft_record.reviews = formatted_reviews
        flag_modified(draft_record, "reviews")
        draft_record.created_at = datetime.now()
        if len(drafts) > 1:
            for old_d in drafts[1:]:
                await db.delete(old_d)
    else:
        biz_cat = matched_biz.category if matched_biz else "Dịch vụ"
        biz_url = matched_biz.url if matched_biz else ""
        
        new_draft = ReviewDraft(
            id=f"draft_{uuid.uuid4().hex[:16]}",
            business_id=target_id,
            business_name=target_name,
            category=biz_cat,
            url=biz_url,
            tone="Nhiệt tình",
            language="vi",
            length="medium",
            custom_keywords=[],
            reviews=formatted_reviews,
            created_at=datetime.now()
        )
        db.add(new_draft)

    await db.commit()

    await log_system_activity(
        db,
        "Cập nhật bài nháp review",
        f"Người dùng {current_user.email} đã cập nhật bài nháp review cho doanh nghiệp ID {business_id}.",
        "success"
    )

    return {
        "statusCode": 200,
        "success": True,
        "data": {
            "message": "Đã cập nhật nội dung bài nháp review thành công vào cơ sở dữ liệu.",
            "reviews": formatted_reviews
        },
        "error": None
    }


@router.delete("/drafts/{business_id}", status_code=status.HTTP_200_OK)
async def delete_business_drafts(
    business_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Xóa toàn bộ bài nháp review của doanh nghiệp khỏi cơ sở dữ liệu (bảng review_drafts).
    """
    matched_biz = await _find_business_by_any_id(db, business_id)
    target_ids = {business_id.lower()}
    target_names = {business_id.lower()}
    if matched_biz:
        target_ids.add(matched_biz.id.lower())
        target_names.add(matched_biz.name.strip().lower())

    result = await db.execute(select(ReviewDraft))
    all_drafts = result.scalars().all()
    drafts = [
        d for d in all_drafts 
        if d.business_id.lower() in target_ids or d.business_name.strip().lower() in target_names
    ]
    
    for d in drafts:
        await db.delete(d)
        
    await db.commit()

    await log_system_activity(
        db,
        "Xóa bài nháp review",
        f"Người dùng {current_user.email} đã xóa bài nháp review của doanh nghiệp ID {business_id}.",
        "info"
    )

    return {
        "statusCode": 200,
        "success": True,
        "data": {
            "message": "Đã xóa toàn bộ bài nháp của doanh nghiệp thành công."
        },
        "error": None
    }


@router.post("/post-success", status_code=status.HTTP_201_CREATED)
async def record_post_success(
    payload: PostSuccessRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Ghi nhận bài review đã được ĐĂNG THÀNH CÔNG lên Google Maps vào bảng review_history.
    """
    result = await db.execute(select(Business).where(Business.id == payload.business_id))
    business = result.scalars().first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin doanh nghiệp."
        )

    # 1. Tạo bản ghi đăng bài thành công trong review_history
    history_id = f"hist_{uuid.uuid4().hex[:16]}"
    posted_review_item = {
        "id": f"rev_{uuid.uuid4().hex[:8]}",
        "rating": payload.rating,
        "content": payload.review_text,
        "gmail": payload.gmail,
        "proxy": payload.proxy,
        "images": payload.images or [],
        "posted_at": datetime.now().isoformat()
    }

    new_history = ReviewHistory(
        id=history_id,
        business_id=business.id,
        business_name=business.name,
        category=business.category,
        url=business.url,
        tone="Nhiệt tình",
        language="vi",
        length="medium",
        custom_keywords=[],
        reviews=[posted_review_item],
        created_at=datetime.now()
    )
    db.add(new_history)

    # 2. Ghi log hệ thống
    await log_system_activity(
        db,
        "Đăng review thành công",
        f"Người dùng {current_user.email} đã hoàn tất đăng review thành công cho '{business.name}' qua Gmail {payload.gmail}.",
        "success"
    )

    await db.commit()

    return {
        "message": "Đã ghi nhận bài đăng thành công vào Lịch sử bài viết review.",
        "history_id": history_id
    }


class PostAutoRequest(BaseModel):
    business_id: str
    gmail: str
    proxy: str
    rating: int = 5
    review_text: str
    images: list[str] = []
    record_history: bool = False
    auto_submit: bool = True
    headless: bool = False

@router.post("/post-auto", status_code=status.HTTP_200_OK)
async def post_review_auto_backend(
    payload: PostAutoRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Tự động hóa ngầm quy trình đăng bài review bằng Python Playwright tại Backend.
    """
    result = await db.execute(select(Business).where(Business.id == payload.business_id))
    business = result.scalars().first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin doanh nghiệp."
        )

    # 1. Gọi dịch vụ tự động hóa ngầm Playwright Python
    from app.services.poster import auto_post_review

    valid_images = [img for img in (payload.images or []) if os.path.exists(img)]

    poster_res = await auto_post_review(
        db=db,
        user_email=current_user.email,
        business_name=business.name,
        place_id=business.place_id,
        url=business.url,
        address=business.address,
        rating=payload.rating,
        content=payload.review_text,
        gmail=payload.gmail,
        proxy_str=payload.proxy,
        images=valid_images,
        headless=payload.headless,
        auto_submit=payload.auto_submit
    )

    if not poster_res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=poster_res.get("message", "Tự động đăng review ngầm thất bại.")
        )

    # 2. Ghi nhận bài đã đăng vào review_history (Chỉ tạo mới khi record_history=True)
    history_id = None
    if payload.record_history:
        history_id = f"hist_{uuid.uuid4().hex[:16]}"
        posted_review_item = {
            "id": f"rev_{uuid.uuid4().hex[:8]}",
            "rating": payload.rating,
            "content": payload.review_text,
            "images": payload.images if payload.images else poster_res.get("images", []),
            "gmail": payload.gmail,
            "proxy": payload.proxy,
            "posted_at": datetime.now().isoformat()
        }

        new_history = ReviewHistory(
            id=history_id,
            business_id=business.id,
            business_name=business.name,
            category=business.category,
            url=business.url,
            tone="Nhiệt tình",
            language="vi",
            length="medium",
            custom_keywords=[],
            reviews=[posted_review_item],
            created_at=datetime.now()
        )
        db.add(new_history)
        await db.commit()

    return {
        "success": True,
        "posted": poster_res.get("posted", False),
        "message": poster_res.get("message"),
        "history_id": history_id
    }
