from datetime import datetime
from pydantic import Field
from app.schemas.base import BaseModelConfig

class ReviewGenerateRequest(BaseModelConfig):
    business_id: str = Field(..., description="ID của doanh nghiệp trong cơ sở dữ liệu")
    tone: str = Field(..., description="Tông giọng của review (vd: Nhiệt tình, Khách quan,...)")
    language: str = Field(..., description="Ngôn ngữ của review (vd: Tiếng Việt, Tiếng Anh,...)")
    length: str = Field(..., description="Độ dài của review (Ngắn, Vừa, Dài)")
    quantity: int = Field(3, description="Số lượng câu review cần sinh", ge=1, le=1000)
    focus_keywords: list[str] = Field(default=[], description="Danh sách từ khóa bắt buộc chèn vào review")
    
    # Cấu hình tự động lên lịch sau khi sinh
    auto_schedule: bool = Field(default=False, description="Tự động đặt lịch đăng review")
    schedule_start_at: datetime | None = Field(default=None, description="Thời gian bắt đầu đặt lịch")
    min_interval_hours: int = Field(24, ge=1, description="Khoảng cách giờ tối thiểu")
    max_interval_hours: int = Field(48, ge=1, description="Khoảng cách giờ tối đa")
    schedule_auto_submit: bool = Field(default=True, description="Tự động bấm đăng")
    schedule_headless: bool = Field(default=False, description="Chạy ngầm ẩn trình duyệt")

class GeneratedReviewItem(BaseModelConfig):
    id: int | str
    rating: int
    content: str
    images: list[str] = []
    gmail: str | None = None
    proxy: str | None = None
    status: str | None = None
    statusText: str | None = None

class ReviewHistoryCreate(BaseModelConfig):
    business_id: str = Field(..., description="ID của doanh nghiệp")
    business_name: str = Field(..., description="Tên doanh nghiệp")
    category: str | None = Field(None, description="Lĩnh vực hoạt động")
    url: str | None = Field(None, description="URL Google Maps")
    tone: str = Field("Nhiệt tình", description="Tông giọng")
    language: str = Field("vi", description="Ngôn ngữ")
    length: str = Field("medium", description="Độ dài")
    custom_keywords: list[str] = Field(default=[], description="Từ khóa đã dùng")
    reviews: list[GeneratedReviewItem] = Field(..., description="Danh sách các bài review đã đăng")

class ReviewHistoryResponse(BaseModelConfig):
    id: str
    business_id: str
    business_name: str
    category: str | None = None
    url: str | None = None
    tone: str
    language: str
    length: str
    custom_keywords: list[str]
    reviews: list[GeneratedReviewItem]
    created_at: datetime

class ReviewScheduleCreate(BaseModelConfig):
    business_id: str
    gmail: str
    proxy: str
    rating: int = 5
    review_text: str
    images: list[str] = []
    scheduled_at: datetime
    auto_submit: bool = True
    headless: bool = False

class ReviewScheduleResponse(BaseModelConfig):
    id: str
    business_id: str
    business_name: str
    gmail: str
    proxy: str
    rating: int
    review_text: str
    images: list[str]
    scheduled_at: datetime
    auto_submit: bool
    headless: bool
    status: str
    status_text: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewScheduleAutoCreate(BaseModelConfig):
    business_id: str
    start_at: datetime
    min_interval_hours: int = Field(24, ge=1)
    max_interval_hours: int = Field(48, ge=1)
    auto_submit: bool = True
    headless: bool = False
