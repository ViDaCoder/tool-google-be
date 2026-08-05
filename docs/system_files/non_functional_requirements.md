# ĐẶC TẢ YÊU CẦU PHI CHỨC NĂNG (NON-FUNCTIONAL REQUIREMENTS)

**Dự án**: Tool Sinh Review Đánh Giá Doanh Nghiệp Google Maps (Google Maps Review Generator)  
**Phiên bản**: 0.0.4  
**Tác giả**: Antigravity AI  

---

## 1. PHÂN LOẠI CÁC YÊU CẦU PHI CHỨC NĂNG

Tài liệu này quy định các tiêu chuẩn chất lượng, giới hạn kỹ thuật và yêu cầu vận hành cho hệ thống Tool sinh Review Google Maps, chia làm các nhóm chính:

1. **Hiệu năng & Thời gian phản hồi (Performance & Latency)**
2. **Khả năng thu thập dữ liệu & Chống block (Scraping Resilience)**
3. **Chất lượng & Độ tự nhiên của Nội dung AI (AI Content Quality)**
4. **Bảo mật & Quản lý Phân quyền (Security & Access Control)**
5. **Độ sẵn sàng & Chịu lỗi (Availability & Fault Tolerance)**
6. **Khả năng mở rộng & Chuẩn hóa (Scalability & Standards)**
7. **Khả năng sử dụng (Usability & User Experience)**

---

## 2. CHI TIẾT CÁC YÊU CẦU PHI CHỨC NĂNG

### 2.1 NFR-01: Hiệu năng & Thời gian phản hồi (Performance & Latency)

| Mã yêu cầu | Tiêu chí | Ngưỡng chỉ tiêu (Threshold Target) | Ghi chú |
| --- | --- | --- | --- |
| **NFR-01.1** | Thời gian Validation & Parse URL | ≤ 300 ms | Kiểm tra định dạng URL Google Maps. |
| **NFR-01.2** | Thời gian Cào dữ liệu (Scraping Time) | ≤ 5 - 8 giây | Thu thập các trường dữ liệu thô của địa điểm. |
| **NFR-01.3** | Thời gian Phân tích ngữ cảnh (Business Analyzer) | ≤ 1 - 2 giây | Tổng hợp JSON Context. |
| **NFR-01.4** | Thời gian Sinh Review từ AI (LLM Generation Time) | ≤ 3 - 6 giây (cho 5-10 câu review) | Sử dụng Streaming Response nếu sinh số lượng lớn. |
| **NFR-01.5** | Tổng thời gian hoàn tất luồng (End-to-End Latency) | ≤ 10 - 15 giây | Từ lúc gửi URL đến khi hiển thị đầy đủ review. |
| **NFR-01.6** | Tải đồng thời hệ thống (Throughput) | Tối thiểu 50 requests/phút | Có cơ chế Queue/Worker hỗ trợ xử lý không nghẽn. |

---

### 2.2 NFR-02: Khả năng thu thập dữ liệu & Chống Block (Scraping Resilience)

- **Xoay vòng Proxy (Proxy Rotation)**:
  - Hệ thống crawler phải tích hợp cơ chế xoay vòng IP / Proxy để tránh bị Google Maps chặn (Rate-limiting/IP Ban).
- **Giả lập Trình duyệt (User-Agent & Fingerprint Rotation)**:
  - Tự động thay đổi User-Agent, Window Size và HTTP Headers ngẫu nhiên hợp lệ khi gửi request.
- **Xử lý Captcha / Anti-Bot**:
  - Nếu gặp phải cơ chế CAPTCHA hoặc chướng ngại vật chống bot từ Google, hệ thống phải tự động retry với Proxy/Session mới (tối đa 3 lần).
- **Cơ chế Cache dữ liệu địa điểm (Data Caching)**:
  - Dữ liệu địa điểm Google Maps của cùng 1 URL sẽ được cache trong vòng 24-48 giờ (Redis/Database) để giảm thiểu số lần cào lại không cần thiết.

---

### 2.3 NFR-03: Chất lượng & Độ tự nhiên của Nội dung AI (AI Quality & Naturalness)

- **Độ đa dạng ngữ nghĩa (Diversity)**:
  - Các câu review được sinh ra trong cùng một lượt phải có cấu trúc câu, từ ngữ xưng hô (ví dụ: "mình", "em", "gia đình mình", "tôi") và góc nhìn trải nghiệm hoàn toàn khác nhau.
- **Tránh Pattern Spammed AI (Anti-AI Footprint)**:
  - Prompt phải quy định nghiêm ngặt loại bỏ các từ ngữ mang tính AI tiêu chuẩn (như "Tóm lại", "Tối ưu", "Nói chung là", "Là một khách hàng...").
- **Sử dụng Từ khóa chính xác (Context Relevance)**:
  - Nội dung sinh ra phải phù hợp 100% với ngành nghề của địa điểm.

---

### 2.4 NFR-04: Bảo mật & Quản lý Phân quyền (Security & Access Control)

- **Chính sách Không Đăng ký Công khai (No Public Register)**:
  - Vô hiệu hóa/Không cung cấp endpoint Đăng ký tài khoản công khai. Tất cả tài khoản chỉ được khởi tạo bởi Quản trị viên (`role = admin`).
- **Mã hóa Mật khẩu (Password Hashing)**:
  - Mật khẩu do Admin khởi tạo hoặc đặt lại cho người dùng phải được mã hóa 1 chiều bằng Bcrypt (với Salt Factor ≥ 10) hoặc Argon2 trước khi lưu vào CSDL.
- **Xác thực qua JWT & Phân quyền Role-based (RBAC)**:
  - Access Token (JWT) thời hạn 24h. Phân biệt rõ quyền `admin` (quản lý user, khóa/mở khóa) và `user` (sinh review, xem lịch sử cá nhân).
- **Bảo vệ Endpoint & Rate Limiting**:
  - Giới hạn thử đăng nhập tối đa 5 lần thất bại trong 15 phút từ cùng 1 IP để chống Brute-force.
- **Bảo mật AI API Keys**:
  - API Keys của AI Provider được bảo mật trong biến môi trường (`.env`), không để lộ ra phía Frontend.
- **Không can thiệp tự động đăng bài (No Auto-Posting Policy)**:
  - **Không tích hợp bất kỳ mã nguồn nào tự động gửi dữ liệu đánh giá lên tài khoản Google của người dùng hay Google Maps Graph API**.

---

### 2.5 NFR-05: Độ sẵn sàng & Chịu lỗi (Availability & Fault Tolerance)

- **Độ sẵn sàng hệ thống (System Availability)**: Đạt chỉ tiêu **99.5% Uptime** đối với API Service.
- **Cơ chế Fallback Provider cho AI (Multi-LLM Resilience)**:
  - Cấu hình danh sách AI Provider ưu tiên: `Primary: OpenAI (GPT-4o-mini / GPT-4o)` ──► `Fallback: Google Gemini (Gemini 1.5 Flash)` ──► `Fallback 2: Claude API`.

---

### 2.6 NFR-06: Khả năng mở rộng & Chuẩn hóa (Scalability & Standards)

- **Chuẩn hóa REST API**:
  - API trả về định dạng JSON chuẩn kèm mã phản hồi HTTP (`status_code`: 200, 201, 400, 401, 403, 429, 500).

---

### 2.7 NFR-07: Khả năng sử dụng & Trải nghiệm Người dùng (Usability & UX)

- **Giao diện Quản trị dành cho Admin**: Trang quản lý danh sách user và đặt lại mật khẩu trực quan.
- **Thao tác đơn giản**: Tối đa 3 cú nhấp chuột để thu được danh sách review.
- **Hỗ trợ Mẫu cấu hình (Preset Templates)**: Cho phép tải bộ tham số yêu thích nhanh chóng.
- **Sao chép 1-Click**: Có nút sao chép thuận tiện kèm Toast notification thông báo.
