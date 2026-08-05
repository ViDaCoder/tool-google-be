import sys
import asyncio

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.future import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.hash_service import HashService
from app.middlewares.response_envelope import (
    ResponseEnvelopeMiddleware,
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)
from app.api.auth import router as auth_router
from app.api.admin_users import router as admin_users_router
from app.api.admin_gmails import router as admin_gmails_router
from app.api.admin_proxies import router as admin_proxies_router
from app.api.business import router as business_router
from app.api.review import router as review_router
from app.api.settings import router as settings_router
from app.api.history import router as history_router
from app.api.admin_logs import router as admin_logs_router

# Cơ chế Lifespan thay thế cho startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP TASKS ---
    print("[Startup] System is starting up...")
    
    # Tạo tự động tài khoản Admin mặc định và bảng cấu hình nếu chưa tồn tại
    async with AsyncSessionLocal() as db:
        try:
            from sqlalchemy import text
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """))
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS review_drafts (
                    id VARCHAR(100) PRIMARY KEY,
                    business_id VARCHAR(100) NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    business_name VARCHAR(255) NOT NULL,
                    category VARCHAR(255),
                    url TEXT,
                    tone VARCHAR(50) NOT NULL,
                    language VARCHAR(10) NOT NULL,
                    length VARCHAR(20) NOT NULL,
                    custom_keywords JSON NOT NULL,
                    reviews JSON NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS gmail_proxies (
                    id SERIAL PRIMARY KEY,
                    gmail_id INTEGER NOT NULL UNIQUE REFERENCES gmail_accounts(id) ON DELETE CASCADE,
                    proxy_id INTEGER NOT NULL REFERENCES proxies(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            await db.commit()
            
            admin_email = "Admin123@gmail.com".strip().lower()
            result = await db.execute(select(User).where(User.email == admin_email))
            admin_user = result.scalars().first()
            
            if not admin_user:
                print(f"[Startup] Default admin user not found. Seeding: {admin_email}...")
                # Sử dụng HashService thông qua thực thể cụ thể
                hash_service = HashService()
                new_admin = User(
                    email=admin_email,
                    password_hash=hash_service.hash_password("Admin@123"),
                    full_name="Quản trị viên",
                    role="admin",
                    is_active=True
                )
                db.add(new_admin)
                await db.commit()
                print(f"[Startup] Default admin user seeded successfully!")
            else:
                print(f"[Startup] Default admin user '{admin_email}' already exists.")
        except Exception as e:
            await db.rollback()
    # Khởi chạy tác vụ chạy ngầm định kỳ 1 tiếng (3600s) kiểm tra sức khỏe Proxy
    async def periodic_proxy_checker():
        while True:
            try:
                await asyncio.sleep(3600)
                print("[Background Proxy Checker] Starting hourly health check for all proxies...")
                from app.services.proxy_checker import check_all_proxies_health
                async with AsyncSessionLocal() as db:
                    await check_all_proxies_health(db)
            except asyncio.CancelledError:
                print("[Background Proxy Checker] Task cancelled.")
                break
            except Exception as e:
                print(f"[Background Proxy Checker Error] {e}")

    checker_task = asyncio.create_task(periodic_proxy_checker())

    yield
    # --- SHUTDOWN TASKS ---
    checker_task.cancel()
    print("[Shutdown] System is shutting down...")

# Khởi tạo FastAPI với lifespan
app = FastAPI(
    title="ReviewGen API Backend",
    description="Backend API phục vụ hệ thống sinh review tự động Google Maps",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Cấu hình CORS cho phép kết nối từ mọi IP trong mạng LAN
raw_origins = [origin.strip() for origin in settings.ALLOW_ORIGINS.split(",") if origin.strip()] if settings.ALLOW_ORIGINS else ["*"]
if "*" in raw_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    cors_origins = []
    for o in raw_origins:
        cors_origins.append(o.rstrip("/"))
        cors_origins.append(f"{o.rstrip('/')}/")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Phục vụ file tĩnh tĩnh cho ảnh upload
import os
from fastapi.staticfiles import StaticFiles
os.makedirs("uploads/reviews", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Đăng ký Response Envelope Middleware
app.add_middleware(ResponseEnvelopeMiddleware)

# Đăng ký các Exception Handlers chuẩn hóa
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Đăng ký các API Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_users_router, prefix="/api/v1")
app.include_router(admin_gmails_router, prefix="/api/v1")
app.include_router(admin_proxies_router, prefix="/api/v1")
app.include_router(business_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(history_router, prefix="/api/v1")
app.include_router(admin_logs_router, prefix="/api/v1")

@app.get("/", tags=["System"])
async def root():
    return {
        "message": "ReviewGen API Backend is running.",
        "documentation": "/docs"
    }

@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "ReviewGen Backend",
        "database": "PostgreSQL (Connected)"
    }


if __name__ == "__main__":
    import uvicorn
    import uvicorn.config
    
    # Vá lỗi (Monkey-patch) Uvicorn trên Windows để không ép buộc SelectorEventLoop,
    # giúp Playwright khởi chạy trình duyệt (subprocess) bình thường.
    original_setup = uvicorn.config.Config.setup_event_loop
    def custom_setup(self, *args, **kwargs):
        original_setup(self, *args, **kwargs)
        if sys.platform == "win32":
            import asyncio
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                print("[Uvicorn Patch] Forced WindowsProactorEventLoopPolicy successfully.")
            except Exception as e:
                print(f"[Uvicorn Patch Warning] Failed to force ProactorEventLoopPolicy: {e}")
                
    uvicorn.config.Config.setup_event_loop = custom_setup

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)