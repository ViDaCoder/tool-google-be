from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

# Khởi tạo Async Engine kết nối PostgreSQL
engine = create_async_engine(
    settings.async_database_url,
    echo=False,  # Đặt True nếu muốn in câu lệnh SQL ra terminal khi debug
    future=True
)

# Khởi tạo session maker để tạo các phiên làm việc bất đồng bộ
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Dependency cung cấp DB Session cho các API Endpoint của FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
