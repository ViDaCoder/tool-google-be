from datetime import datetime
from sqlalchemy import String, Text, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class ReviewDraft(Base):
    __tablename__ = "review_drafts"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # vd: draft_xxx
    business_id: Mapped[str] = mapped_column(String(100), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    length: Mapped[str] = mapped_column(String(20), nullable=False)
    custom_keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    reviews: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # Mảng các câu nháp review được sinh bởi AI
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
