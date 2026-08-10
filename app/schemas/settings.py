from pydantic import Field
from app.schemas.base import BaseModelConfig

class SystemSettingsResponse(BaseModelConfig):
    analytics_api_key: str = Field("", description="Google Gemini API Key cho động cơ Analytics")
    analytics_model_id: str = Field("gemini-2.5-flash", description="Mã mô hình AI cho động cơ Analytics")
    analytics_system_prompt: str = Field("", description="System Prompt chỉ thị cho động cơ Analytics")
    
    review_api_key: str = Field("", description="Google Gemini API Key cho động cơ Review")
    review_model_id: str = Field("gemini-1.5-pro", description="Mã mô hình AI cho động cơ Review")
    review_system_prompt: str = Field("", description="System Prompt chỉ thị cho động cơ Review")
    image_folder_path: str = Field(r"C:\hinh_google", description="Đường dẫn thư mục gốc chứa ảnh doanh nghiệp")

class SystemSettingsUpdate(BaseModelConfig):
    analytics_api_key: str | None = Field(None, description="Google Gemini API Key cho động cơ Analytics")
    analytics_model_id: str | None = Field(None, description="Mã mô hình AI cho động cơ Analytics")
    analytics_system_prompt: str | None = Field(None, description="System Prompt chỉ thị cho động cơ Analytics")
    
    review_api_key: str | None = Field(None, description="Google Gemini API Key cho động cơ Review")
    review_model_id: str | None = Field(None, description="Mã mô hình AI cho động cơ Review")
    review_system_prompt: str | None = Field(None, description="System Prompt chỉ thị cho động cơ Review")
    image_folder_path: str | None = Field(None, description="Đường dẫn thư mục gốc chứa ảnh doanh nghiệp")
