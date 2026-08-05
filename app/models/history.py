from datetime import datetime
from sqlalchemy import String, Text, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class ReviewHistory(Base):
    __tablename__ = "review_history"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # vd: hist_xxx
    business_id: Mapped[str] = mapped_column(String(100), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone: Mapped[str] = mapped_column(String(50), nullable=False)  # "Nhiệt tình", "Khách quan", etc.
    language: Mapped[str] = mapped_column(String(10), nullable=False)  # "vi", "en"
    length: Mapped[str] = mapped_column(String(20), nullable=False)  # "short", "medium", "long"
    custom_keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # Mảng keyword người dùng truyền vào
    reviews: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # Mảng review được sinh [{id, rating, content}]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
