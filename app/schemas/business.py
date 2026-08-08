from datetime import datetime
from pydantic import Field, HttpUrl, field_validator
from app.schemas.base import BaseModelConfig

class BusinessParseRequest(BaseModelConfig):
    url: str = Field(..., description="Đường dẫn Google Maps của doanh nghiệp")

    @field_validator("url")
    @classmethod
    def validate_google_maps_url(cls, v: str) -> str:
        url_clean = v.strip()
        if not url_clean.startswith("http") or "google.com/maps" not in url_clean:
            raise ValueError("Đường dẫn phải bắt đầu bằng http/https và thuộc tên miền google.com/maps.")
        return url_clean

class BusinessResponse(BaseModelConfig):
    id: str
    place_id: str
    url: str
    name: str
    category: str
    address: str
    rating_score: float
    review_count: int
    extracted_keywords: list[str]
    raw_reviews_sample: list[str]
    analysis_info: str | None = None
    review_strategy: str | None = None
    image_folder: str | None = None
    created_at: datetime
    updated_at: datetime
