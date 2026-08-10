import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete

from app.database import get_db
from app.models.business import Business
from app.models.schedule import ReviewSchedule
from app.schemas.review import ReviewScheduleCreate, ReviewScheduleResponse
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
    
    # Đảm bảo scheduled_at lớn hơn thời gian hiện tại
    scheduled_at = payload.scheduled_at
    if scheduled_at.tzinfo is not None:
        scheduled_at = scheduled_at.astimezone().replace(tzinfo=None)

    if scheduled_at <= datetime.now():
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Thời gian đặt lịch đăng bài phải ở tương lai."
         )

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
