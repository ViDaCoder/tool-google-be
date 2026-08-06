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

        # Gán trực tiếp từng Gmail khả dụng chưa dùng cho bài nháp tương ứng
        for idx, r in enumerate(reviews):
            if idx < len(fresh_gmails):
                assigned_gmail = fresh_gmails[idx].email
                r["gmail"] = assigned_gmail
                r["proxy"] = proxy_map.get(assigned_gmail.lower(), "IP Máy chủ (Direct)")
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
        images=payload.images
    )

    if not poster_res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=poster_res.get("message", "Tự động đăng review ngầm thất bại.")
        )

    # 2. Ghi nhận bài đã đăng vào review_history (Chỉ tạo mới khi record_history=True)
    if payload.record_history:
        history_id = f"hist_{uuid.uuid4().hex[:16]}"
        posted_review_item = {
            "id": f"rev_{uuid.uuid4().hex[:8]}",
            "rating": payload.rating,
            "content": payload.review_text,
            "images": payload.images,
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
