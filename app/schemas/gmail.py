from datetime import datetime
from pydantic import Field, field_validator
import re
from app.schemas.base import BaseModelConfig

class GmailCreate(BaseModelConfig):
    email: str = Field(..., description="Địa chỉ email Gmail")
    password: str = Field(..., min_length=1, description="Mật khẩu của tài khoản Gmail")
    status: str = Field("Hoạt động", description="Trạng thái của tài khoản Gmail ('Hoạt động', 'Bị khóa', 'Cần xác minh')")

    @field_validator("email")
    @classmethod
    def validate_gmail(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@gmail\.com$", v_clean):
            raise ValueError("Email phải là địa chỉ Gmail hợp lệ (kết thúc bằng @gmail.com).")
        return v_clean

class GmailUpdate(BaseModelConfig):
    password: str | None = Field(None, description="Mật khẩu mới của tài khoản Gmail (nếu muốn cập nhật)")
    status: str = Field(..., description="Trạng thái của tài khoản Gmail ('Hoạt động', 'Bị khóa', 'Cần xác minh')")

class GmailResponse(BaseModelConfig):
    id: int
    email: str
    status: str
    proxy: str | None = None
    created_at: datetime
    updated_at: datetime

class GmailBulkCreateRequest(BaseModelConfig):
    raw_text: str = Field(..., description="Nội dung danh sách Gmail dán vào (mỗi tài khoản 1 dòng)")

