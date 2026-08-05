from datetime import datetime
from pydantic import Field
from app.schemas.base import BaseModelConfig

class ProxyCreate(BaseModelConfig):
    ip: str = Field(..., description="Địa chỉ IP của Proxy")
    port: int = Field(..., ge=1, le=65535, description="Cổng kết nối của Proxy")
    username: str | None = Field(None, description="Tên đăng nhập Proxy (nếu có)")
    password: str | None = Field(None, description="Mật khẩu đăng nhập Proxy (nếu có)")
    status: str = Field("Hoạt động", description="Trạng thái Proxy ('Hoạt động', 'Không hoạt động')")

class ProxyUpdate(BaseModelConfig):
    ip: str = Field(..., description="Địa chỉ IP của Proxy")
    port: int = Field(..., ge=1, le=65535, description="Cổng kết nối của Proxy")
    username: str | None = Field(None, description="Tên đăng nhập Proxy (nếu có)")
    password: str | None = Field(None, description="Mật khẩu đăng nhập Proxy (nếu có)")
    status: str = Field(..., description="Trạng thái Proxy ('Hoạt động', 'Không hoạt động')")

class ProxyResponse(BaseModelConfig):
    id: int
    ip: str
    port: int
    username: str | None
    password: str | None
    status: str
    assigned_gmails: list[str] = []
    created_at: datetime
    updated_at: datetime
