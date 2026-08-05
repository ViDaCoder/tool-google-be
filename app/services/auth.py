from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.interface.token_service import ITokenService
from app.services.token_service import TokenService
from app.interface.hash_service import IHashService
from app.services.hash_service import HashService
from app.interface.crypto_service import ICryptoService
from app.services.crypto_service import CryptoService
from app.interface.scraper import BaseScraper
from app.services.scraper import HttpRequestScraper
from app.interface.llm import BaseLLMClient
from app.AI.gemini import GeminiClient

# Chuẩn Bearer Token của FastAPI
oauth2_scheme = HTTPBearer()

# --- DEPENDENCY INJECTIONS PROVIDERS ---
def get_token_service() -> ITokenService:
    """Dependency cung cấp thực thể TokenService thông qua interface ITokenService."""
    return TokenService()

def get_hash_service() -> IHashService:
    """Dependency cung cấp thực thể HashService thông qua interface IHashService."""
    return HashService()

def get_crypto_service() -> ICryptoService:
    """Dependency cung cấp thực thể CryptoService thông qua interface ICryptoService."""
    return CryptoService()

def get_scraper() -> BaseScraper:
    """Dependency cung cấp thực thể HttpRequestScraper thông qua interface BaseScraper."""
    return HttpRequestScraper()

def get_llm_client() -> BaseLLMClient:
    """Dependency cung cấp thực thể GeminiClient thông qua interface BaseLLMClient."""
    return GeminiClient()

# --- FASTAPI SECURITY DEPENDENCIES ---
async def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    token_service: ITokenService = Depends(get_token_service),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency lấy ra đối tượng User hiện tại đang đăng nhập.
    Tự động kiểm tra JWT token hợp lệ và tài khoản có đang hoạt động thông qua ITokenService.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token xác thực không hợp lệ hoặc đã hết hạn.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Giải mã JWT qua token service interface
    payload = token_service.decode_access_token(token.credentials)
    if payload is None:
        raise credentials_exception
        
    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception
        
    # Truy vấn thông tin người dùng từ database
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản này đã bị khóa."
        )
        
    return user

async def admin_required(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency bắt buộc vai trò người dùng hiện tại phải là 'admin'.
    Nếu không phải admin sẽ lập tức trả về lỗi 403 Forbidden.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thực hiện hành động này (Chỉ dành cho Admin)."
        )
    return current_user
