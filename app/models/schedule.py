from datetime import datetime
from sqlalchemy import String, Text, JSON, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class ReviewSchedule(Base):
    __tablename__ = "review_schedules"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # vd: sched_xxx
    business_id: Mapped[str] = mapped_column(String(100), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    gmail: Mapped[str] = mapped_column(String(255), nullable=False)
    proxy: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[int] = mapped_column(default=5, nullable=False)
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    images: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    auto_submit: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    headless: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending, processing, success, failed
    status_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
