# ĐẶC TẢ YÊU CẦU CHỨC NĂNG HỆ THỐNG (FUNCTIONAL REQUIREMENTS)

**Dự án**: Tool Sinh Review Đánh Giá Doanh Nghiệp Google Maps (Google Maps Review Generator)  
**Phiên bản**: 0.0.4  
**Tác giả**: Antigravity AI  

---

## 1. TỔNG QUAN VÀ PHẠM VI HỆ THỐNG

### 1.1 Mục tiêu hệ thống

Hệ thống được phát triển nhằm hỗ trợ các chủ doanh nghiệp, nhà tiếp thị (marketers) hoặc chuyên viên truyền thông trong việc tự động thu thập thông tin doanh nghiệp từ Google Maps, phân tích ngữ cảnh/lĩnh vực hoạt động, và sử dụng Trí tuệ nhân tạo (AI/LLM) để sinh ra các nội dung đánh giá (review) chất lượng, đa dạng, chân thực.

### 1.2 Phạm vi chức năng (Scope)

- **Bao gồm (IN SCOPE)**:
  - Quản lý tài khoản người dùng bởi **Quản trị viên (Admin)**: Admin trực tiếp khởi tạo tài khoản, kích hoạt/khóa tài khoản hoặc hỗ trợ đặt lại mật khẩu cho người dùng.
  - Xác thực hệ thống: Đăng nhập, Đăng xuất, Cấp lại Access Token (Refresh Token).
  - Thu thập dữ liệu doanh nghiệp công khai từ liên kết (URL) Google Maps.
  - Phân tích ngành nghề, đặc điểm dịch vụ/sản phẩm và ngữ cảnh doanh nghiệp.
  - Sinh chuỗi câu đánh giá/review ngẫu nhiên hoặc theo tiêu chí cấu hình.
  - Cho phép tùy chỉnh tông giọng, ngôn ngữ, từ khóa nhấn mạnh, độ dài review và lưu thành Mẫu cấu hình (Preset Templates).
  - Cung cấp tính năng Sao chép (Copy), Chỉnh sửa (Edit), Xuất dữ liệu (Export) và Lưu trữ lịch sử sinh review theo tài khoản.
- **Không bao gồm (OUT OF SCOPE)**:
  - **KHÔNG CÓ TÍNH NĂNG ĐĂNG KÝ TỰ DO (Self-Registration)**: Hệ thống **không có chức năng đăng ký công khai**. Tất cả tài khoản người dùng chỉ được tạo và cấp bởi Quản trị viên (Admin).
  - **KHÔNG TÍNH CREDIT / HẠN NGẠCH LƯỢT DÙNG**: Hệ thống không quản lý credit hay giới hạn số lượt sinh review của người dùng.
  - **TỰ ĐỘNG ĐĂNG BÀI/REVIEW LÊN GOOGLE MAPS**: Hệ thống **tuyệt đối không** tự động đăng review lên Google Maps (không can thiệp vào tài khoản Google người dùng, không sử dụng bot tự động gửi review lên Google Maps API hay Selenium auto-post).

---

## 2. DANH SÁCH CÁC CHỨC NĂNG (USE CASE OVERVIEW)

| Mã Use Case | Tên Use Case | Mô tả ngắn |
| --- | --- | --- |
| **UC-01** | Quản lý Xác thực tài khoản | Đăng nhập, Đăng xuất, Cấp lại Access Token (Refresh Token). |
| **UC-02** | Thu thập dữ liệu địa điểm từ URL | Nhận URL Google Maps, trích xuất dữ liệu thô và chi tiết của địa điểm. |
| **UC-03** | Phân tích & Trích xuất thông tin doanh nghiệp | Xử lý dữ liệu thô, nhận diện lĩnh vực, đặc điểm nổi bật và đánh giá hiện tại. |
| **UC-04** | Sinh câu đánh giá/review tự động bằng AI | Gửi prompt ngữ cảnh đến LLM Engine để sinh nội dung review theo cấu hình. |
| **UC-05** | Tùy chỉnh tham số sinh Review | Điều chỉnh Tông giọng, Ngôn ngữ, Độ dài, Từ khóa bắt buộc trong nội dung. |
| **UC-06** | Quản lý & Thao tác câu Review | Chỉnh sửa, Sao chép (Copy), Sinh lại (Regenerate) hoặc Xuất danh sách review. |
| **UC-07** | Quản lý Lịch sử tra cứu & Sinh Review | Tra cứu lại các lần sinh review trước đó theo tài khoản cá nhân. |
| **UC-08** | Quản lý Mẫu cấu hình (Preset Templates) | Lưu, chỉnh sửa và tải lại bộ cấu hình sinh review yêu thích cho các lần sau. |
| **UC-09** | Quản lý Người dùng bởi Admin | Admin tạo tài khoản mới, đặt lại mật khẩu, khóa/mở khóa tài khoản người dùng. |

---

## 3. CHI TIẾT CÁC CHỨC NĂNG HỆ THỐNG

### 3.1 UC-01: Quản lý Xác thực (Đăng nhập, Đăng xuất, Refresh Token)

- **Người thực hiện**: Người dùng (User / Admin)
- **Mục đích**: Cho phép người dùng đăng nhập bằng tài khoản do Admin cấp để truy cập các tính năng sinh review, lưu trữ lịch sử cá nhân và duy trì phiên làm việc an toàn.
- **Các luồng chức năng chi tiết**:
  - **3.1.1 Đăng nhập (Login)**:
    - *Input*: Email và Mật khẩu (do Admin cấp).
    - *Main Flow*: Đối chiếu thông tin -> Kiểm tra trạng thái hoạt động tài khoản (`is_active = true`) -> Trả về Access Token (JWT) và Refresh Token -> Lưu thông tin phiên phía Client.
    - *Exception*: Sai thông tin hoặc Tài khoản bị khóa (`is_active = false`) -> Thông báo lỗi tương ứng.
  - **3.1.2 Cấp lại Access Token (Refresh Token)**:
    - *Input*: Refresh Token còn hiệu lực.
    - *Main Flow*: Xác thực Refresh Token -> Cấp mới Access Token (thời hạn 24h) mà người dùng không cần đăng nhập lại.
  - **3.1.3 Đăng xuất (Logout)**:
    - *Input*: Access Token hiện tại.
    - *Main Flow*: Thu hồi Refresh Token -> Làm sạch Token phía Client -> Chuyển về trang Đăng nhập.

---

### 3.2 UC-02: Thu thập dữ liệu địa điểm từ URL Google Maps

- **Người thực hiện**: Người dùng (User / Admin)
- **Mục đích**: Nhập đường dẫn địa điểm doanh nghiệp trên Google Maps để hệ thống tự động cào/trích xuất thông tin cơ bản.
- **Đầu vào (Input)**:
  - Chuỗi liên kết (URL) địa điểm Google Maps.
- **Quy trình xử lý (Main Flow)**:
  1. Người dùng nhập URL và nhấn nút "Phân tích địa điểm".
  2. Hệ thống kiểm tra cú pháp (Validation) URL.
  3. Mô-đun Crawler kích hoạt trình thu thập dữ liệu (HTTP Client / Headless Browser).
  4. Trích xuất: Tên doanh nghiệp, Địa chỉ, Danh mục/Ngành nghề, Điểm đánh giá, Tổng số review, Mẫu review hiện tại.
  5. Trả về kết quả hiển thị lên giao diện.

---

### 3.3 UC-03: Phân tích & Trích xuất thông tin doanh nghiệp (Business Analyzer)

- **Người thực hiện**: Hệ thống (Background Engine)
- **Mục đích**: Tổng hợp dữ liệu thu thập được từ **UC-02** để xây dựng bộ hồ sơ ngữ cảnh (Context Profile) cho doanh nghiệp.
- **Quy trình xử lý (Main Flow)**:
  1. Tiếp nhận dữ liệu thô từ **UC-02**.
  2. Phân tích ngữ nghĩa: Nhóm ngành nghề cốt lõi, từ khóa nổi bật (ví dụ: "món ăn ngon", "phục vụ chu đáo"), đối tượng khách hàng.
  3. Tổng hợp thành cấu trúc **Business Context JSON** làm đầu vào cho LLM Engine.

---

### 3.4 UC-04: Sinh câu đánh giá/review tự động bằng AI (LLM Engine)

- **Người thực hiện**: Người dùng / Hệ thống
- **Mục đích**: Sinh ra chuỗi các đoạn review hoàn chỉnh, phong phú dựa trên hồ sơ ngữ cảnh doanh nghiệp.
- **Đầu vào (Input)**:
  - Business Context JSON (từ **UC-03**).
  - Cấu hình tham số sinh review (từ **UC-05**).
  - Số lượng review cần sinh (ví dụ: 5, 10 câu).
- **Quy trình xử lý (Main Flow)**:
  1. Lắp ráp Prompt Engineering chứa ngữ cảnh doanh nghiệp và quy tắc tránh trùng lặp.
  2. Gửi yêu cầu tới AI Model (OpenAI / Gemini / Claude API).
  3. Trả về danh sách câu review hiển thị lên màn hình.

---

### 3.5 UC-05: Tùy chỉnh tham số sinh Review (Review Customization)

- **Người thực hiện**: Người dùng
- **Mục đích**: Cho phép người dùng linh hoạt điều chỉnh kết quả review theo nhu cầu.
- **Các tham số tùy chỉnh**:
  - **Tông giọng (Tone of Voice)**: Nhiệt tình, Chuyên nghiệp, Thân thiện, Hài hước.
  - **Mức đánh giá (Rating level)**: 5 sao, 4 sao.
  - **Độ dài câu (Review Length)**: Ngắn (1-2 câu), Vừa (3-5 câu), Dài (chi tiết).
  - **Ngôn ngữ (Language)**: Tiếng Việt, Tiếng Anh, Tiếng Hàn, Tiếng Nhật,...
  - **Từ khóa nhấn mạnh (Focus Keywords)**: Các từ khóa bắt buộc xuất hiện trong câu review.

---

### 3.6 UC-06: Quản lý & Thao tác với kết quả Review

- **Người thực hiện**: Người dùng
- **Mục đích**: Xem, chỉnh sửa, sao chép và quản lý các câu review đã sinh.
- **Các chức năng chi tiết**:
  - **Sao chép nhanh (One-click Copy)**: Copy từng câu review hoặc toàn bộ danh sách vào Clipboard.
  - **Chỉnh sửa trực tiếp (Inline Edit)**: Sửa đổi văn bản trực tiếp trên giao diện.
  - **Tạo lại câu này (Regenerate Item)**: Sinh lại 1 câu review cụ thể nếu chưa ưng ý.
  - **Đánh giá Thích / Không thích**: Phản hồi chất lượng câu review.

---

### 3.7 UC-07: Quản lý Lịch sử & Lưu trữ (History & Export)

- **Người thực hiện**: Người dùng
- **Mục đích**: Lưu lại danh sách các doanh nghiệp đã tra cứu và các câu review đã sinh theo tài khoản cá nhân.
- **Các chức năng chi tiết**:
  - Xem danh sách lịch sử tra cứu, tìm kiếm/lọc theo tên hoặc ngày.
  - Xuất dữ liệu (Export) sang định dạng `.txt`, `.csv` hoặc `.json`.
  - Xóa bản ghi lịch sử.

---

### 3.8 UC-08: Quản lý Mẫu cấu hình (Preset Templates)

- **Người thực hiện**: Người dùng
- **Mục đích**: Lưu lại bộ tham số tùy chỉnh (Tone, Độ dài, Ngôn ngữ, Từ khóa mẫu) thành các Preset Template để sử dụng nhanh lần sau.
- **Chức năng chi tiết**:
  - **Lưu Preset Mới**: Người dùng chọn các tham số và nhấn "Lưu thành mẫu mới".
  - **Tải Preset**: Chọn mẫu đã lưu từ danh sách thả xuống để tự động điền các tham số.
  - **Xóa / Sửa Preset**: Quản lý danh sách các mẫu cấu hình cá nhân.

---

### 3.9 UC-09: Quản lý Người dùng bởi Admin (Admin User Management)

- **Người thực hiện**: Quản trị viên (Admin)
- **Mục đích**: Admin trực tiếp quản lý toàn bộ tài khoản người dùng trong hệ thống.
- **Các chức năng chi tiết**:
  - **Tạo tài khoản mới**: Admin nhập Email, Mật khẩu ban đầu, Họ tên và Role để khởi tạo tài khoản cho người dùng.
  - **Đặt lại mật khẩu (Reset Password)**: Admin hỗ trợ reset mật khẩu cho người dùng khi được yêu cầu.
  - **Khóa / Mở khóa tài khoản**: Chuyển trạng thái `is_active` của tài khoản để cho phép hoặc vô hiệu hóa quyền truy cập hệ thống.

---

## 4. TỔNG HỢP LUỒNG DỮ LIỆU CHÍNH (MAIN DATA FLOW)

```
[Admin Tạo Tài Khoản (UC-09)] ──► Khởi tạo User trong CSDL
       │
       ▼
[Đăng nhập / Auth (UC-01)] ──► JWT Access Token
       │
       ▼
[URL Google Maps] 
       │
       ▼
(UC-02: Thu thập Dữ liệu) ──► Trích xuất Tên, Ngành nghề, Ratings, Samples
       │
       ▼
(UC-03: Phân tích Doanh nghiệp) ──► Tạo Business Context JSON
       │
       ▼
(UC-05 & UC-08: Chọn / Tải Preset Tham số) ──► Kết hợp Tone, Ngôn ngữ, Length, Keywords
       │
       ▼
(UC-04: Sinh Review AI) ──► LLM Engine sinh chuỗi Review
       │
       ▼
(UC-06: Thao tác Review) ──► Xem / Chỉnh sửa / Copy câu review
       │
       ▼
(UC-07: Lưu Lịch sử theo User & Export) ──► Lưu DB / Xuất File TXT, CSV
```
