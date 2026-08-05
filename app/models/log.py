from datetime import datetime
from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    meta: Mapped[str] = mapped_column(Text, nullable=False)  # Chi tiết thông tin log (ví dụ: lỗi traceback, IP, tài khoản thực hiện)
    log_type: Mapped[str] = mapped_column(String(50), default="info", nullable=False)  # "info", "user", "success", "error"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
