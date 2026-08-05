from sqlalchemy.ext.asyncio import AsyncSession
from app.models.log import SystemLog

async def log_system_activity(db: AsyncSession, title: str, meta: str, log_type: str = "info"):
    """
    Ghi nhận log bất đồng bộ vào cơ sở dữ liệu.
    Các loại log_type hỗ trợ: 'info', 'user', 'success', 'error'
    """
    try:
        new_log = SystemLog(
            title=title,
            meta=meta,
            log_type=log_type
        )
        db.add(new_log)
        await db.commit()
        # In song song ra terminal để quản trị viên theo dõi
        print(f"[System Log - {log_type.upper()}] {title}: {meta[:150]}")
    except Exception as e:
        print(f"[System Log Error] Failed to write log to Database: {e}")
