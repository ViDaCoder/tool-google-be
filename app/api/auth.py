from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.schemas.auth import UserLogin, TokenResponse, UserShortInfo
from app.interface.hash_service import IHashService
from app.interface.token_service import ITokenService
from app.services.auth import get_hash_service, get_token_service

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin, 
    db: AsyncSession = Depends(get_db),
    hash_service: IHashService = Depends(get_hash_service),
    token_service: ITokenService = Depends(get_token_service)
):
    """
    Xác thực thông tin đăng nhập của người dùng.
    Trả về JWT Access Token nếu thành công.
    """
    # Tìm kiếm user theo email
    result = await db.execute(select(User).where(User.email.ilike(credentials.email.strip())))
    user = result.scalars().first()
    
    from app.services.logs import log_system_activity

    if not user:
        await log_system_activity(db, "Đăng nhập thất bại", f"Tài khoản không tồn tại: {credentials.email}", "error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tài khoản không tồn tại trên hệ thống."
        )
        
    if not user.is_active:
        await log_system_activity(db, "Đăng nhập thất bại", f"Tài khoản bị khóa: {credentials.email}", "error")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản của bạn đã bị khóa."
        )
        
    # Xác thực mật khẩu qua Interface HashService
    if not hash_service.verify_password(credentials.password, user.password_hash):
        await log_system_activity(db, "Đăng nhập thất bại", f"Sai mật khẩu cho tài khoản: {credentials.email}", "error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu không chính xác."
        )
        
    # Tạo JWT token mã hóa email qua Interface TokenService
    access_token = token_service.create_access_token(data={"sub": user.email})
    
    await log_system_activity(
        db, 
        "Đăng nhập thành công", 
        f"Người dùng {user.full_name} ({user.email}) có vai trò '{user.role}' đăng nhập hệ thống.", 
        "user"
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserShortInfo(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role
        )
    )
