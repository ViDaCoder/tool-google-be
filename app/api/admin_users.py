from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.interface.hash_service import IHashService
from app.services.auth import admin_required, get_hash_service

router = APIRouter(prefix="/admin/users", tags=["Admin User Management"], dependencies=[Depends(admin_required)])

@router.get("", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    """Lấy danh sách tất cả người dùng trong hệ thống (Chỉ dành cho Admin)."""
    result = await db.execute(select(User).order_by(User.id.desc()))
    users = result.scalars().all()
    return users

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate, 
    db: AsyncSession = Depends(get_db),
    hash_service: IHashService = Depends(get_hash_service)
):
    """
    Tạo người dùng mới (Chỉ dành cho Admin).
    Mật khẩu khởi tạo mặc định sẽ là 'Password123!'.
    """
    # Kiểm tra trùng lặp email
    result = await db.execute(select(User).where(User.email == user_data.email.strip().lower()))
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email này đã được đăng ký bởi một tài khoản khác."
        )
        
    # Tạo user mới với mật khẩu mặc định đã băm qua Interface
    default_password_hash = hash_service.hash_password("Demo@123")
    
    new_user = User(
        email=user_data.email.strip().lower(),
        password_hash=default_password_hash,
        full_name=user_data.full_name.strip(),
        role=user_data.role,
        is_active=True
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int, 
    user_data: UserUpdate, 
    db: AsyncSession = Depends(get_db),
    hash_service: IHashService = Depends(get_hash_service)
):
    """Cập nhật thông tin người dùng (Chỉ dành cho Admin)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin người dùng."
        )
        
    user.full_name = user_data.full_name.strip()
    user.role = user_data.role
    user.is_active = user_data.is_active

    if user_data.password and user_data.password.strip():
        user.password_hash = hash_service.hash_password(user_data.password.strip())
    
    await db.commit()
    await db.refresh(user)
    return user

@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    hash_service: IHashService = Depends(get_hash_service)
):
    """Reset mật khẩu người dùng về mặc định 'Demo@123' (Chỉ dành cho Admin)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin người dùng."
        )
        
    user.password_hash = hash_service.hash_password("Demo@123")
    await db.commit()
    
    return {
        "success": True,
        "message": "Đã reset mật khẩu về mặc định 'Demo@123' thành công."
    }

@router.delete("/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Xóa tài khoản người dùng khỏi hệ thống (Chỉ dành cho Admin)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin người dùng."
        )
        
    await db.delete(user)
    await db.commit()
    
    return {
        "success": True,
        "message": "Đã xóa người dùng khỏi hệ thống thành công."
    }
