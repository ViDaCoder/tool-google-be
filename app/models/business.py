from datetime import datetime
from sqlalchemy import String, Float, Integer, Text, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # vd: biz_xxx
    place_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    rating_score: Mapped[float] = mapped_column(Float, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # Mảng các keyword
    raw_reviews_sample: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # Các review mẫu cào được
    analysis_info: Mapped[str | None] = mapped_column(Text, nullable=True)  # Thông tin phân tích tổng hợp
    review_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)  # Kịch bản review đề xuất
    image_folder: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Đường dẫn thư mục hình ảnh
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

