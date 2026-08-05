from datetime import datetime
from app.schemas.base import BaseModelConfig

class UserCreate(BaseModelConfig):
    email: str
    full_name: str
    role: str = "user"  # "admin" hoặc "user"

class UserUpdate(BaseModelConfig):
    full_name: str
    role: str
    is_active: bool
    password: str | None = None

class UserResponse(BaseModelConfig):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
