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
