from datetime import datetime
from sqlalchemy import Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class GmailProxy(Base):
    __tablename__ = "gmail_proxies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    gmail_id: Mapped[int] = mapped_column(ForeignKey("gmail_accounts.id", ondelete="CASCADE"), unique=True, nullable=False)
    proxy_id: Mapped[int] = mapped_column(ForeignKey("proxies.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

