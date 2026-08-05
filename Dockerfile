FROM python:3.11-slim

# Thiết lập môi trường không tạo file .pyc và không buffer log
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Cài đặt các thư viện hệ thống cần thiết cho PostgreSQL & Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy file requirements.txt và cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cài đặt trình duyệt Playwright Chromium kèm theo thư viện phụ thuộc của Linux
RUN playwright install --with-deps chromium

# Copy toàn bộ mã nguồn ứng dụng Backend vào container
COPY . .

EXPOSE 8000

# Khởi chạy FastAPI Uvicorn Server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
