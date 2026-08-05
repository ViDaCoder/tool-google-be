# NGUYÊN TẮC THIẾT KẾ & QUY TẮC PHÁT TRIỂN MÃ NGUỒN BACKEND

Dự án: **Hệ thống sinh review tự động Google Maps (ReviewGen Backend)**  
Ngôn ngữ: **Python 3.10+**  
Framework: **FastAPI**

Tài liệu này định nghĩa cấu trúc thư mục, quy tắc viết code, luồng xử lý dữ liệu và các tiêu chuẩn bảo mật bắt buộc phải tuân thủ trong quá trình phát triển mã nguồn backend.

---

## 1. CẤU TRÚC THƯ MỤC HỆ THỐNG (DIRECTORY STRUCTURE)

Backend được tổ chức theo mô hình phân lớp (Layered Architecture) rõ ràng nhằm tăng khả năng bảo trì, mở rộng và viết Unit Test độc lập.

```text
c:\tool-google-be\
├── app/
│   ├── AI/               # Chứa các client kết nối LLM (Gemini API, OpenAI)
│   ├── api/              # Chứa các Route định nghĩa API (Router / Controller)
│   ├── interface/        # Các lớp trừu tượng (Interface/Abstract Class)
│   ├── middleware/       # Custom Middlewares (JWT Auth, CORS, Logger)
│   ├── models/           # Định nghĩa các Model Database (SQLAlchemy ORM - PostgreSQL)
│   ├── schemas/          # Định nghĩa Pydantic Schemas (Validation dữ liệu vào/ra)
│   ├── services/         # Chứa Business Logic cốt lõi (Scraper, Database CRUD, LLM Processing)
│   └── main.py           # Điểm khởi chạy ứng dụng (Entrypoint)
├── docs/                 # Tài liệu thiết kế hệ thống
│   ├── principles/       # Thư mục chứa tài liệu nguyên tắc code
│   │   └── coding_principles.md  # File này
├── requirement.txt       # Danh sách thư viện phụ thuộc của Python
└── venv/                 # Môi trường ảo Python (Virtual Environment)
```

### Chi tiết vai trò từng thư mục:
*   `main.py`: Khởi tạo ứng dụng FastAPI, gắn kết Router, cấu hình CORS, xử lý ngoại lệ toàn cục (Global Exception Handler) và đăng ký Middlewares.
*   `api/`: Định nghĩa các API endpoints (ví dụ: `/api/v1/auth`, `/api/v1/reviews`). Đóng vai trò là tầng **Controller** tiếp nhận Request, kiểm tra đầu vào sơ bộ qua Pydantic Schema, sau đó gọi trực tiếp các Interfaces/Services và trả về kết quả cho Frontend.
*   `services/`: Lớp chứa logic nghiệp vụ nặng nhất (như tương tác với mô hình AI, chạy tác vụ cào dữ liệu Google Maps, tính toán các chỉ số kinh doanh).
*   `models/`: Khai báo cấu trúc bảng cơ sở dữ liệu vật lý.
*   `schemas/`: Chứa các schema của Pydantic để Validate dữ liệu đầu vào (Request Body) và định dạng dữ liệu đầu ra (Response Body).
*   `AI/`: Đóng gói (encapsulate) các kết nối API tới Google Gemini. Sử dụng Prompt Template để tạo nội dung review chất lượng.
*   `interface/`: Định nghĩa các interface/abstract classes (ví dụ: `BaseLLMClient`, `BaseScraper`) để dễ dàng hoán đổi nhà cung cấp (ví dụ: sẵn sàng cho các mô hình AI khác mà không ảnh hưởng tới logic nghiệp vụ).

---

## 2. QUY TẮC VIẾT CODE (CODING STANDARDS)

### 2.1 Chuẩn Định Dạng Code
*   **PEP 8 Compliance:** Bắt buộc tuân thủ quy tắc PEP 8 (sử dụng 4 khoảng trắng để thụt lề, đặt tên hàm/biến bằng `snake_case`, đặt tên Class bằng `PascalCase`).
*   **Type Hinting:** Mọi khai báo hàm đều phải khai báo kiểu dữ liệu cho tham số đầu vào và kiểu dữ liệu trả về.
    ```python
    async def get_user_by_email(email: str) -> User | None:
        ...
    ```
*   **Docstrings:** Các hàm nghiệp vụ phức tạp bắt buộc phải có Docstring mô tả mục đích, tham số đầu vào và kết quả trả về.

### 2.2 Xử lý Bất đồng bộ (Async/Await)
*   Sử dụng `async/await` cho tất cả các tác vụ liên quan đến I/O (Truy vấn DB, gọi API bên thứ ba như Gemini, gọi proxy, đọc/ghi file).
*   Khi sử dụng thư viện HTTP client, bắt buộc dùng `httpx.AsyncClient` thay thế cho `requests`.

### 2.3 Dependency Injection (FastAPI Depends)
*   Tận dụng cơ chế `Depends` của FastAPI để quản lý kết nối Database Session, kiểm tra quyền truy cập (Auth Guard), hoặc khởi tạo dịch vụ.
    ```python
    @router.post("/generate")
    async def generate_review(
        request: ReviewGenerateRequest,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db_session)
    ):
        ...
    ```

### 2.4 Nguyên tắc Thiết kế Interface (Trừu tượng hóa)
*   **Bắt buộc định nghĩa Interface trước:** Trước khi bắt tay viết các Service hoặc Client tích hợp (như Scraper, LLM provider, Database Handler), bắt buộc phải định nghĩa Interface (Abstract Base Class sử dụng thư viện `abc` của Python) trong thư mục `app/interface/`.
*   **Không hardcode logic vào Interface:** Tuyệt đối không viết code xử lý thực tế (implementation logic) vào trong file interface. File interface chỉ chứa các định nghĩa hàm trừu tượng (`@abstractmethod`), mô tả ngắn gọn chức năng, kiểu dữ liệu tham số đầu vào và kiểu dữ liệu trả về.
*   **Code triển khai ở nơi khác:** Việc viết code logic thực tế phải được đặt ở các thư mục tương ứng khác (như `services/` hoặc `AI/`) bằng cách kế thừa interface đó.
    ```python
    # Đúng (Trong app/interface/llm.py):
    from abc import ABC, abstractmethod

    class BaseLLMClient(ABC):
        @abstractmethod
        async def generate_text(self, prompt: str) -> str:
            """Mô tả ngắn gọn chức năng sinh văn bản từ Prompt"""
            pass
            
    # Đúng (Trong app/AI/gemini.py):
    from app.interface.llm import BaseLLMClient

    class GeminiClient(BaseLLMClient):
        async def generate_text(self, prompt: str) -> str:
            # Code triển khai gọi API thực tế ở đây
            return actual_api_call(prompt)
    ```

### 2.5 Cấu trúc Module hóa (__init__.py)
*   **Bắt buộc có file `__init__.py`:** Mỗi thư mục con bên trong `app/` (và các thư mục con cấp dưới nếu có) bắt buộc phải chứa một tệp tin trống `__init__.py`.
*   **Mục đích:** Đóng gói các thư mục này thành các Python Package/Module hợp lệ. Điều này giúp các lệnh import hoạt động ổn định, rõ ràng và ngăn ngừa lỗi `ModuleNotFoundError` khi chạy ứng dụng cũng như khi chạy unit test.

---

## 3. LUỒNG XỬ LÝ DỮ LIỆU & ĐỊNH DẠNG PHẢN HỒI (DATA FLOW & RESPONSE FORMAT)

### 3.1 Luồng xử lý tuần tự (Standard Data Flow)
```text
[Client (Frontend)] ──► [API Routes / Controller] ──► [Services (Interfaces)] ──► [Database / AI Engine]
```

### 3.2 Quy ước JSON Naming & Định dạng phản hồi
*   **Bên trong Backend (Python):** Sử dụng `snake_case`.
*   **Giao diện API (JSON gửi đi/nhận về):** Thống nhất dùng `camelCase` để khớp với quy ước viết code của Frontend (Javascript/React).
*   **Cách cấu hình tự động bằng Pydantic Alias Generator ở Backend:**
    ```python
    from pydantic import BaseModel, ConfigDict
    from pydantic.alias_generators import to_camel

    class BaseModelConfig(BaseModel):
        model_config = ConfigDict(
            alias_generator=to_camel,
            populate_by_name=True,
            from_attributes=True
        )
    ```
*   **Định dạng phản hồi chuẩn (Standard JSON API Response):**
    ```json
    {
      "statusCode": 200,
      "success": true,
      "data": { ... },
      "error": null
    }
    ```
    Nếu xảy ra lỗi:
    ```json
    {
      "statusCode": 400,
      "success": false,
      "data": null,
      "error": {
        "code": "VALIDATION_ERROR",
        "message": "Chi tiết thông báo lỗi hiển thị cho người dùng."
      }
    }
    ```

---

## 4. XỬ LÝ LỖI TOÀN CỤC (GLOBAL EXCEPTION HANDLING)

*   Không để lộ các thông báo lỗi thô (Raw Traceback) của Python ra ngoài API.
*   Xây dựng lớp ngoại lệ tùy chỉnh (`AppException`) kế thừa từ `Exception`.
*   Sử dụng `@app.exception_handler(AppException)` trong `main.py` để bắt và chuyển đổi tất cả các lỗi nghiệp vụ về định dạng chuẩn ở mục 3.2 trước khi trả về Client.

---

## 5. BẢO MẬT & XÁC THỰC (SECURITY & AUTHENTICATION)

1.  **Mã hóa mật khẩu:** Tuyệt đối không lưu mật khẩu dạng clear-text. Sử dụng `bcrypt` với Salt Factor $\ge 10$ hoặc `argon2` để băm mật khẩu trước khi lưu xuống Database.
2.  **JWT Authentication:**
    *   Sử dụng Bearer JWT Token để xác thực các request.
    *   Hạn dùng Access Token tối đa là 24h.
    *   Mã hóa JWT bắt buộc phải dùng thuật toán `HS256` kèm theo Secret Key lưu trong biến môi trường `.env`.
3.  **Phân quyền dựa trên vai trò (RBAC):**
    *   Phân biệt rạch ròi 2 quyền: `admin` (Quản lý User, Gmail, Proxy, xem Logs hệ thống) và `user` (Sinh review, Xem lịch sử).
    *   Sử dụng FastAPI Dependency để chặn quyền truy cập trái phép ở tầng Route API.

---

## 6. QUẢN LÝ BIẾN MÔI TRƯỜNG (.env)

*   Mọi thông tin nhạy cảm (Secret Key, Connection String DB, API Key Gemini, Proxy List mật khẩu) bắt buộc phải cấu hình trong file `.env` ngoài thư mục gốc và được load thông qua `pydantic-settings`.
*   Không được commit file `.env` thực tế lên Git (đã khai báo trong `.gitignore`). Hãy cung cấp một file `.env.example` chứa các key trống để làm mẫu cấu hình.
