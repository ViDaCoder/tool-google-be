from abc import ABC, abstractmethod

class BaseLLMClient(ABC):
    """
    Interface trừu tượng cho LLM Client tương tác với Gemini AI.
    """
    @abstractmethod
    async def analyze_business(self, name: str, category: str, address: str, reviews: list[str]) -> dict:
        """
        Phân tích thông tin và các review mẫu của doanh nghiệp để đưa ra:
        - Tóm tắt phân tích (analysis_info)
        - Chiến lược viết review (review_strategy)
        - Từ khóa nổi bật tự động phân tích (extracted_keywords)
        
        Đầu vào:
            name (str): Tên doanh nghiệp.
            category (str): Lĩnh vực hoạt động.
            address (str): Địa chỉ doanh nghiệp.
            reviews (list[str]): Danh sách review mẫu cào được.
        Đầu ra:
            dict: {
                "analysis_info": str,
                "review_strategy": str,
                "extracted_keywords": list[str]
            }
        """
        pass

    @abstractmethod
    async def generate_reviews(
        self,
        business_details: dict,
        tone: str,
        language: str,
        length: str,
        quantity: int,
        focus_keywords: list[str]
    ) -> list[dict]:
        """
        Sinh danh sách các câu review dựa theo cấu hình yêu cầu.
        """
        pass

    @abstractmethod
    async def resolve_business_details(self, name_hint: str, coordinates_hint: str = None) -> dict:
        """
        Sử dụng tri thức của LLM để phân tích và tìm thông tin thực tế của doanh nghiệp 
        khi cào dữ liệu Google Maps thất bại/bị chặn.
        
        Đầu vào:
            name_hint (str): Tên gợi ý của doanh nghiệp.
            coordinates_hint (str): Tọa độ gợi ý từ URL.
        Đầu ra:
            dict: {
                "name": str,
                "category": str,
                "address": str,
                "rating_score": float,
                "review_count": int,
                "raw_reviews_sample": list[str]
            }
        """
        pass
