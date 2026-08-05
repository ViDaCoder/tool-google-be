from abc import ABC, abstractmethod

class BaseScraper(ABC):
    """
    Interface trừu tượng cho Scraper cào dữ liệu Google Maps.
    """
    @abstractmethod
    async def parse_url(self, url: str, proxy: str | None = None) -> dict:
        """
        Cào thông tin doanh nghiệp từ URL Google Maps.
        Đầu vào:
            url (str): Link Google Maps doanh nghiệp.
            proxy (str | None): Chuỗi proxy sử dụng nếu có (dạng http://host:port hoặc http://user:pass@host:port).
        Đầu ra:
            dict chứa thông tin doanh nghiệp cào được:
            {
                "place_id": str,
                "name": str,
                "category": str,
                "address": str,
                "rating_score": float,
                "review_count": int,
                "extracted_keywords": list[str],
                "raw_reviews_sample": list[str]
            }
        """
        pass
