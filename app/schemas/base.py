from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class BaseModelConfig(BaseModel):
    """
    Lớp cấu hình cơ sở cho Pydantic Models.
    Tự động chuyển đổi thuộc tính Python (snake_case) sang JSON API (camelCase)
    khi serialize/deserialize dữ liệu gửi nhận với Frontend.
    """
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )
