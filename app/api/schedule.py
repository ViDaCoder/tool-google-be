import uuid
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete

from app.database import get_db
from app.models.business import Business
from app.models.schedule import ReviewSchedule
from app.schemas.review import ReviewScheduleCreate, ReviewScheduleResponse, ReviewScheduleAutoCreate
from app.services.auth import get_current_user
from app.services.logs import log_system_activity

router = APIRouter(prefix="/reviews/schedule", tags=["Review Schedules"])

@router.post("", response_model=ReviewScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_review_schedule(
    payload: ReviewScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Đặt lịch tự động đăng bài review cho doanh nghiệp.
    """
    # 1. Kiểm tra doanh nghiệp tồn tại
    biz_res = await db.execute(select(Business).where(Business.id == payload.business_id))
    business = biz_res.scalars().first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin doanh nghiệp."
        )

    # 2. Tạo bản ghi đặt lịch mới
    schedule_id = f"sched_{uuid.uuid4().hex[:16]}"
    
    # Đảm bảo scheduled_at lớn hơn thời gian hiện tại và nằm trong khung giờ 9h-18h
    scheduled_at = payload.scheduled_at
    if scheduled_at.tzinfo is not None:
        scheduled_at = scheduled_at.astimezone().replace(tzinfo=None)
    scheduled_at = scheduled_at.replace(second=0, microsecond=0)

    if scheduled_at <= datetime.now():
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Thời gian đặt lịch đăng bài phải ở tương lai."
         )

    if scheduled_at.hour < 9 or scheduled_at.hour > 18 or (scheduled_at.hour == 18 and scheduled_at.minute > 0):
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Thời gian đặt lịch đăng bài phải nằm trong khung giờ từ 9h đến 18h."
         )

    # Tránh trùng lặp lịch đăng trong toàn bộ hệ thống (Collision Avoidance)
    sched_times_res = await db.execute(
        select(ReviewSchedule.scheduled_at).where(ReviewSchedule.status == "pending")
    )
    booked_times = [row[0] for row in sched_times_res.all()]
    
    current_time = scheduled_at.replace(second=0, microsecond=0)
    while True:
        conflict = False
        for booked_time in booked_times:
            diff = abs((current_time - booked_time.replace(second=0, microsecond=0)).total_seconds())
            if diff < 300:  # Khoảng cách tối thiểu 5 phút
                conflict = True
                break
        if conflict:
            current_time = current_time + timedelta(minutes=random.randint(5, 15))
        else:
            scheduled_at = current_time
            break

    new_schedule = ReviewSchedule(
        id=schedule_id,
        business_id=payload.business_id,
        gmail=payload.gmail,
        proxy=payload.proxy,
        rating=payload.rating,
        review_text=payload.review_text,
        images=payload.images,
        scheduled_at=scheduled_at,
        auto_submit=payload.auto_submit,
        headless=payload.headless,
        status="pending",
        status_text=None,
        user_email=current_user.email,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    db.add(new_schedule)
    await db.commit()
    await db.refresh(new_schedule)

    await log_system_activity(
        db,
        "Đặt lịch đăng review",
        f"Người dùng {current_user.email} đã đặt lịch đăng bài review cho '{business.name}' vào lúc {payload.scheduled_at} qua Gmail {payload.gmail}.",
        "info"
    )

    # Trả về Response
    return ReviewScheduleResponse(
        id=new_schedule.id,
        business_id=new_schedule.business_id,
        business_name=business.name,
        gmail=new_schedule.gmail,
        proxy=new_schedule.proxy,
        rating=new_schedule.rating,
        review_text=new_schedule.review_text,
        images=new_schedule.images,
        scheduled_at=new_schedule.scheduled_at,
        auto_submit=new_schedule.auto_submit,
        headless=new_schedule.headless,
        status=new_schedule.status,
        status_text=new_schedule.status_text,
        created_at=new_schedule.created_at,
        updated_at=new_schedule.updated_at
    )

@router.get("", response_model=list[ReviewScheduleResponse])
async def get_review_schedules(
    business_id: str | None = None,
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Lấy danh sách các lịch đăng review (có thể lọc theo doanh nghiệp và trạng thái).
    """
    stmt = select(ReviewSchedule, Business.name.label("business_name")).join(
        Business, Business.id == ReviewSchedule.business_id
    )
    
    if business_id:
        stmt = stmt.where(ReviewSchedule.business_id == business_id)
    if status_filter:
        stmt = stmt.where(ReviewSchedule.status == status_filter)
        
    stmt = stmt.order_by(ReviewSchedule.scheduled_at.asc())
    
    result = await db.execute(stmt)
    rows = result.all()
    
    response_list = []
    for row in rows:
        sched, biz_name = row
        response_list.append(
            ReviewScheduleResponse(
                id=sched.id,
                business_id=sched.business_id,
                business_name=biz_name,
                gmail=sched.gmail,
                proxy=sched.proxy,
                rating=sched.rating,
                review_text=sched.review_text,
                images=sched.images,
                scheduled_at=sched.scheduled_at,
                auto_submit=sched.auto_submit,
                headless=sched.headless,
                status=sched.status,
                status_text=sched.status_text,
                created_at=sched.created_at,
                updated_at=sched.updated_at
            )
        )
    return response_list

@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
async def delete_review_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Hủy lịch đăng review (chỉ được phép hủy khi trạng thái là pending hoặc failed).
    """
    result = await db.execute(select(ReviewSchedule).where(ReviewSchedule.id == schedule_id))
    schedule = result.scalars().first()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lịch đăng review."
        )
        
    if schedule.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể hủy lịch đăng khi tiến trình đang chạy."
        )

    # Cập nhật lại bài nháp review tương ứng trong DB để đồng bộ trạng thái
    from app.models.draft import ReviewDraft
    draft_res = await db.execute(select(ReviewDraft).where(ReviewDraft.business_id == schedule.business_id))
    draft = draft_res.scalars().first()
    if draft and isinstance(draft.reviews, list):
        updated_reviews = []
        for r in draft.reviews:
            if r.get("scheduleId") == schedule_id or (r.get("gmail") and r.get("gmail").lower() == schedule.gmail.lower()):
                r["status"] = "ready"
                r["statusText"] = None
                if "scheduleId" in r:
                    del r["scheduleId"]
            updated_reviews.append(r)
        draft.reviews = updated_reviews
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(draft, "reviews")

    await db.delete(schedule)
    await db.commit()

    await log_system_activity(
        db,
        "Hủy lịch đăng review",
        f"Người dùng {current_user.email} đã hủy lịch đăng review ID {schedule_id} qua Gmail {schedule.gmail}.",
        "info"
    )

    return {"message": "Đã hủy lịch đăng review thành công."}

@router.post("/{schedule_id}/run", response_model=ReviewScheduleResponse, status_code=status.HTTP_200_OK)
async def run_review_schedule_immediately(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Kích hoạt chạy lịch đăng review ngay lập tức mà không chờ giờ hẹn.
    """
    result = await db.execute(
        select(ReviewSchedule, Business.name.label("business_name")).join(
            Business, Business.id == ReviewSchedule.business_id
        ).where(ReviewSchedule.id == schedule_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lịch đăng review."
        )
        
    schedule, biz_name = row
    
    if schedule.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lịch đăng này đang được thực thi ở tiến trình khác."
        )

    # Đặt lịch hẹn sang thời điểm hiện tại và để background worker quét chạy luôn
    schedule.scheduled_at = datetime.now()
    schedule.status = "pending"
    schedule.status_text = "Đã kích hoạt chạy ngay lập tức..."
    await db.commit()
    await db.refresh(schedule)

    await log_system_activity(
        db,
        "Kích hoạt chạy lịch review ngay lập tức",
        f"Người dùng {current_user.email} đã kích hoạt chạy lịch review ID {schedule_id} ngay lập tức.",
        "info"
    )

    return ReviewScheduleResponse(
        id=schedule.id,
        business_id=schedule.business_id,
        business_name=biz_name,
        gmail=schedule.gmail,
        proxy=schedule.proxy,
        rating=schedule.rating,
        review_text=schedule.review_text,
        images=schedule.images,
        scheduled_at=schedule.scheduled_at,
        auto_submit=schedule.auto_submit,
        headless=schedule.headless,
        status=schedule.status,
        status_text=schedule.status_text,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at
    )


@router.post("/auto", status_code=status.HTTP_201_CREATED)
async def create_auto_batch_schedule(
    payload: ReviewScheduleAutoCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Tự động đặt lịch hàng loạt các bài review nháp chưa đăng theo thời gian giãn cách ngẫu nhiên.
    """
    # 1. Kiểm tra doanh nghiệp tồn tại
    biz_res = await db.execute(select(Business).where(Business.id == payload.business_id))
    business = biz_res.scalars().first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin doanh nghiệp."
        )

    # 2. Tìm bài nháp review của doanh nghiệp
    from app.models.draft import ReviewDraft
    draft_res = await db.execute(select(ReviewDraft).where(ReviewDraft.business_id == payload.business_id))
    draft_record = draft_res.scalars().first()
    if not draft_record or not isinstance(draft_record.reviews, list) or len(draft_record.reviews) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không tìm thấy bài review nháp nào cần đặt lịch."
        )

    # 3. Lọc danh sách các bài nháp ở trạng thái "ready" (chưa đăng, chưa hẹn giờ)
    draft_reviews = draft_record.reviews
    ready_reviews = [r for r in draft_reviews if isinstance(r, dict) and r.get("status") == "ready"]
    
    if len(ready_reviews) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tất cả các bài review nháp đã được đặt lịch hoặc đã đăng thành công."
        )

    # 4. Tính toán thời gian giãn cách
    from sqlalchemy.orm.attributes import flag_modified
    
    start_at = payload.start_at
    if start_at.tzinfo is not None:
        start_at = start_at.astimezone().replace(tzinfo=None)
    start_at = start_at.replace(second=0, microsecond=0)

    if start_at <= datetime.now():
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Thời gian bắt đầu đặt lịch phải ở tương lai."
         )

    # Lấy toàn bộ các mốc thời gian đang chờ (pending) trong hệ thống để tránh trùng lặp
    sched_times_res = await db.execute(
        select(ReviewSchedule.scheduled_at).where(ReviewSchedule.status == "pending")
    )
    booked_times = [row[0] for row in sched_times_res.all()]

    current_scheduled_time = start_at
    created_count = 0

    for idx, r in enumerate(ready_reviews):
        # Tính thời gian đăng bài tiếp theo
        if idx > 0:
            random_hours = random.uniform(payload.min_interval_hours, payload.max_interval_hours)
            current_scheduled_time = current_scheduled_time + timedelta(hours=random_hours)
            current_scheduled_time = current_scheduled_time.replace(second=0, microsecond=0)
        
        # Đảm bảo không trùng lặp / quá sát (Collision Avoidance) và nằm trong dải 9h - 18h
        temp_time = current_scheduled_time.replace(second=0, microsecond=0)
        while True:
            if temp_time.hour < 9:
                temp_time = temp_time.replace(hour=9, minute=random.randint(0, 30))
            elif temp_time.hour > 18 or (temp_time.hour == 18 and temp_time.minute > 0):
                temp_time = (temp_time + timedelta(days=1)).replace(hour=9, minute=random.randint(0, 30))
            
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
        
        # Tạo bản ghi đặt lịch mới
        schedule_id = f"sched_{uuid.uuid4().hex[:16]}"
        new_schedule = ReviewSchedule(
            id=schedule_id,
            business_id=payload.business_id,
            gmail=r.get("gmail", ""),
            proxy=r.get("proxy", "IP Máy chủ (Direct)"),
            rating=r.get("rating", 5),
            review_text=r.get("content", ""),
            images=r.get("images", []),
            scheduled_at=current_scheduled_time,
            auto_submit=payload.auto_submit,
            headless=payload.headless,
            status="pending",
            status_text=None,
            user_email=current_user.email,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(new_schedule)
        created_count += 1
        
        # Cập nhật trạng thái trong bài nháp gốc
        r["status"] = "scheduled"
        r["statusText"] = current_scheduled_time.strftime('%d/%m/%Y %H:%M')
        r["scheduleId"] = schedule_id

    # Lưu thay đổi vào DB
    flag_modified(draft_record, "reviews")
    await db.commit()

    await log_system_activity(
        db,
        "Đặt lịch hàng loạt",
        f"Người dùng {current_user.email} đã tự động đặt lịch hàng loạt {created_count} bài review cho '{business.name}' bắt đầu từ {start_at.strftime('%d/%m/%Y %H:%M')}.",
        "info"
    )

    return {
        "success": True,
        "message": f"Đã đặt lịch thành công cho {created_count} bài review.",
        "count": created_count
    }
