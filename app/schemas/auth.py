from app.schemas.base import BaseModelConfig

class UserLogin(BaseModelConfig):
    email: str
    password: str

class UserShortInfo(BaseModelConfig):
    id: int
    email: str
    full_name: str
    role: str

class TokenResponse(BaseModelConfig):
    access_token: str
    token_type: str = "bearer"
    user: UserShortInfo
