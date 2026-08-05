import sys
import json
import asyncio
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Cấu hình UTF-8 cho stdout/stderr để hỗ trợ tiếng Việt trên Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.config import settings
from app.interface.llm import BaseLLMClient

# --- PYDANTIC SCHEMAS CHO STRUCTURED OUTPUTS ---
class BusinessAnalysisResult(BaseModel):
    analysis_info: str = Field(..., description="Tóm tắt phân tích đặc điểm, thế mạnh, chất lượng dịch vụ của doanh nghiệp dựa trên các reviews thực tế.")
    review_strategy: str = Field(..., description="Chiến lược và định hướng chi tiết để viết các câu review chân thực, tự nhiên và lôi cuốn cho doanh nghiệp này.")
    extracted_keywords: list[str] = Field(..., description="Danh sách từ 3 đến 5 từ khóa cốt lõi, tích cực đại diện cho điểm mạnh lớn nhất của doanh nghiệp.")

class SingleReview(BaseModel):
    rating: int = Field(..., description="Điểm đánh giá bằng sao (từ 4 đến 5 sao, mặc định là 5 sao).")
    content: str = Field(..., description="Nội dung review chi tiết đóng vai khách hàng thực tế trải nghiệm dịch vụ.")

class ReviewGenerationResult(BaseModel):
    reviews: list[SingleReview] = Field(..., description="Danh sách các câu review được sinh ra theo yêu cầu.")


class BusinessResolutionResult(BaseModel):
    name: str = Field(..., description="Tên đầy đủ chính thức của doanh nghiệp tại cơ sở này.")
    category: str = Field(..., description="Lĩnh vực hoạt động chính xác (ví dụ: Cửa hàng cà phê, Nhà hàng buffet, Thẩm mỹ viện).")
    address: str = Field(..., description="Địa chỉ vật lý chính xác của cơ sở này.")
    rating_score: float = Field(..., description="Điểm đánh giá trung bình từ 1.0 đến 5.0.")
    review_count: int = Field(..., description="Tổng số lượng đánh giá thực tế của cơ sở này.")
    raw_reviews_sample: list[str] = Field(..., description="Danh sách 3 đến 5 câu đánh giá thực tế tiêu biểu của khách hàng đối với cơ sở này.")


class GeminiClient(BaseLLMClient):
    """
    Thực thi kết nối và gọi Gemini API sử dụng SDK google-genai chính thức.
    """
    def __init__(self, api_key: str = None, model_id: str = None, system_prompt: str = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model_id or settings.MODEL_ID or "gemini-3.1-flash-lite"
        self.system_prompt = system_prompt
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    async def analyze_business(self, name: str, category: str, address: str, reviews: list[str]) -> dict:
        if not self.api_key or not self.client:
            raise ValueError("Thiếu cấu hình GEMINI_API_KEY trong file .env hoặc Cài đặt hệ thống.")
        reviews_text = "\n".join([f"- {r}" for r in reviews]) if reviews else "Chưa có đánh giá thực tế nào."
        
        prompt = f"""
        Hãy phân tích doanh nghiệp sau đây để xây dựng chiến lược viết review:
        Tên doanh nghiệp: {name}
        Lĩnh vực hoạt động: {category}
        Địa chỉ: {address}
        Các đánh giá thực tế mẫu của khách hàng:
        {reviews_text}
        
        Nhiệm vụ của bạn:
        1. Phân tích đặc điểm và điểm mạnh nổi bật nhất của doanh nghiệp dựa trên các đánh giá mẫu (hoặc dựa trên tên và ngành nghề nếu không có đánh giá mẫu).
        2. Đưa ra chiến lược viết review cụ thể: Nên đóng vai những đối tượng khách hàng nào (ví dụ: gia đình đi ăn cuối tuần, học sinh học bài, cặp đôi đi hẹn hò,...), tập trung khen những khía cạnh nào để thu hút, và phong cách hành văn thế nào để tạo cảm giác tự nhiên nhất.
        3. Trích xuất ra từ 3 đến 5 từ khóa tích cực cốt lõi làm nổi bật lên giá trị của quán (ví dụ: 'đồ uống ngon', 'view hồ tây', 'nhân viên dễ thương').
        """

        def call_api():
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BusinessAnalysisResult,
                    temperature=0.2, # Nhiệt độ thấp cho tác vụ phân tích để đảm bảo tính ổn định
                    system_instruction=self.system_prompt if self.system_prompt else None
                )
            )
            return response.text

        try:
            print(f"[Gemini] Analyzing business '{name}' using Gemini API...")
            resp_text = await asyncio.to_thread(call_api)
            data = json.loads(resp_text)
            
            return {
                "analysis_info": data.get("analysis_info", "").strip(),
                "review_strategy": data.get("review_strategy", "").strip(),
                "extracted_keywords": data.get("extracted_keywords", [])
            }
        except Exception as e:
            print(f"[Gemini Error] Error in analyze_business: {e}")
            raise e

    async def generate_reviews(
        self,
        business_details: dict,
        tone: str,
        language: str,
        length: str,
        quantity: int,
        focus_keywords: list[str]
    ) -> list[dict]:
        if not self.api_key or not self.client:
            raise ValueError("Thiếu cấu hình GEMINI_API_KEY trong file .env hoặc Cài đặt hệ thống.")

        total_needed = max(1, int(quantity))
        BATCH_SIZE = 20  # Mỗi lô sinh tối đa 20 câu để đảm bảo không vượt quá Output Token & đụng trần Rate Limit

        # Chia tổng số câu thành các lô nhỏ
        chunks = []
        remaining = total_needed
        while remaining > 0:
            current_batch = min(remaining, BATCH_SIZE)
            chunks.append(current_batch)
            remaining -= current_batch

        print(f"[Gemini Batching] Generating {total_needed} reviews for '{business_details.get('name')}' in {len(chunks)} batch(es) (chunk sizes: {chunks})...")

        all_reviews = []
        kw_text = f"BẮT BUỘC phải chèn một cách tự nhiên các từ khóa sau vào bài viết: {', '.join(focus_keywords)}" if focus_keywords else "Không yêu cầu từ khóa đặc biệt."

        for batch_idx, chunk_qty in enumerate(chunks):
            prompt = f"""
            Bạn đóng vai là khách hàng đã trực tiếp đến trải nghiệm dịch vụ tại địa điểm dưới đây:
            Tên doanh nghiệp: {business_details.get('name')}
            Lĩnh vực hoạt động: {business_details.get('category')}
            Địa chỉ: {business_details.get('address')}
            Chiến lược viết review đề xuất: {business_details.get('review_strategy')}
            
            Hãy sinh ra đúng {chunk_qty} bài đánh giá (review) khác nhau hoàn toàn, đáp ứng chính xác các yêu cầu cấu hình sau:
            - Tông giọng: {tone}
            - Ngôn ngữ: {language}
            - Độ dài mỗi review: {length} (Ngắn: 1-2 câu ngắn gọn đi thẳng vào vấn đề; Vừa: 3-4 câu chi tiết đầy đủ; Dài: từ 5 câu trở lên mô tả kỹ trải nghiệm).
            - Yêu cầu từ khóa: {kw_text}
            
            Quy tắc viết:
            1. Bài viết phải cực kỳ tự nhiên, sử dụng ngôn từ đời thường như người dùng thật viết (được phép viết tắt nhẹ hoặc dùng từ cảm thán tự nhiên).
            2. Các bài viết không được trùng lặp cấu trúc hay ý chính với nhau.
            3. Điểm số đánh giá (rating) dao động từ 4 đến 5 sao (hầu hết nên là 5 sao).
            """

            def call_api():
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ReviewGenerationResult,
                        temperature=0.85,
                        system_instruction=self.system_prompt if self.system_prompt else None
                    )
                )
                return response.text

            # Thực thi từng batch với cơ chế Retry & Exponential Backoff nếu chạm rate limit 429
            success = False
            for attempt in range(3):
                try:
                    print(f"[Gemini Batch {batch_idx + 1}/{len(chunks)}] Requesting {chunk_qty} reviews (attempt {attempt + 1})...")
                    resp_text = await asyncio.to_thread(call_api)
                    data = json.loads(resp_text)
                    
                    batch_items = data.get("reviews", [])
                    for r in batch_items:
                        all_reviews.append({
                            "id": len(all_reviews) + 1,
                            "rating": r.get("rating", 5),
                            "content": r.get("content", "").strip()
                        })
                    success = True
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    print(f"[Gemini Batch Warning] Attempt {attempt + 1} failed: {e}")
                    if attempt < 2 and ("429" in err_str or "resourceexhausted" in err_str or "quota" in err_str):
                        backoff = (attempt + 1) * 3
                        print(f"[Gemini Backoff] Rate limit hit. Retrying in {backoff}s...")
                        await asyncio.sleep(backoff)
                    elif attempt < 2:
                        await asyncio.sleep(1)
                    else:
                        raise e

            # Nghỉ nhẹ 1.5s giữa các batch để giữ tần suất gọi API ở mức an toàn tuyệt đối
            if batch_idx < len(chunks) - 1 and success:
                await asyncio.sleep(1.5)

        print(f"[Gemini Batching] Successfully generated total {len(all_reviews)} reviews!")
        return all_reviews

    async def resolve_business_details(self, name_hint: str, coordinates_hint: str = None) -> dict:
        if not self.api_key or not self.client:
            raise ValueError("Thiếu cấu hình GEMINI_API_KEY trong file .env hoặc Cài đặt hệ thống.")
        prompt = f"""
        Bạn là chuyên gia về Bản đồ và Địa điểm Google Maps. Hãy sử dụng cơ sở tri thức của mình để tìm kiếm và xác định thông tin thực tế chính xác nhất của doanh nghiệp sau:
        - Tên gợi ý từ URL: {name_hint}
        - Tọa độ địa lý/Khu vực gợi ý: {coordinates_hint or "Không có"}
        
        Nhiệm vụ của bạn là điền đầy đủ và chính xác các thông tin thực tế của cơ sở kinh doanh này trên Google Maps:
        1. Tên chính thức đầy đủ (name)
        2. Lĩnh vực hoạt động chính (category)
        3. Địa chỉ chính xác (address)
        4. Điểm đánh giá trung bình thực tế (rating_score) - Số thực từ 1.0 đến 5.0 (ví dụ: 4.2)
        5. Số lượng review thực tế ước lượng (review_count) - Số nguyên lớn hơn 0
        6. Danh sách 3-5 câu đánh giá thực tế tiêu biểu của khách hàng thực tế (raw_reviews_sample) - Các câu đánh giá viết bằng tiếng Việt tự nhiên và sát thực tế nhất.
        
        Lưu ý quan trọng: Thông tin trả về phải là thông tin có thật hoặc cực kỳ sát với thực tế của địa điểm đó dựa trên tên và khu vực địa lý đã cho. Nếu tên gợi ý là giả lập, không có thật, hoặc vô nghĩa (ví dụ: "Not A Real Place", "NotA-Real-Place", "dummy", "test"), bạn BẮT BUỘC phải trả về name="", category="", address="" và raw_reviews_sample=[].
        """

        def call_api():
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BusinessResolutionResult,
                    temperature=0.2, # Nhiệt độ thấp để đảm bảo tính chính xác thông tin thực tế
                    system_instruction=self.system_prompt if self.system_prompt else None
                )
            )
            return response.text

        try:
            print(f"[Gemini] Resolving business details for '{name_hint}'...")
            resp_text = await asyncio.to_thread(call_api)
            data = json.loads(resp_text)
            
            resolved_name = data.get("name", "").strip()
            resolved_address = data.get("address", "").strip()
            if not resolved_name or not resolved_address or "not a real place" in resolved_name.lower():
                # Trả về giá trị trống để báo hiệu địa điểm không tồn tại
                return {
                    "name": "",
                    "category": "",
                    "address": "",
                    "rating_score": 0.0,
                    "review_count": 0,
                    "raw_reviews_sample": []
                }
            
            return {
                "name": resolved_name,
                "category": data.get("category", "Dịch vụ").strip(),
                "address": resolved_address,
                "rating_score": float(data.get("rating_score", 4.5)),
                "review_count": int(data.get("review_count", 100)),
                "raw_reviews_sample": [r.strip() for r in data.get("raw_reviews_sample", []) if r.strip()]
            }
        except Exception as e:
            print(f"[Gemini Error] Error in resolve_business_details: {e}")
            raise e
