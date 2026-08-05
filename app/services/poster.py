import os
import sys
import re
import time
import subprocess
import asyncio
import urllib.parse
from urllib.parse import urlparse
from app.services.logs import log_system_activity

# Reconfigure stdout/stderr for Unicode on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def get_chrome_path() -> str:
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return "chrome.exe"

def find_free_port() -> int:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]
    except Exception:
        return 9223


def _playwright_sync_post(
    user_data_dir: str,
    proxy_config: dict | None,
    target_url: str,
    fallback_url: str | None,
    target_rating: int,
    content: str,
    images: list[str] = None,
    headless: bool = False
) -> bool:
    """
    Khởi chạy Google Chrome nguyên bản bằng subprocess cho tài khoản Gmail có sẵn để đăng bài.
    Sử dụng chung 100% Profile & cấu hình với chức năng Nạp phiên giúp giữ trạng thái ĐÃ ĐĂNG NHẬP.
    Playwright kết nối ngầm qua Remote Debugging Port (CDP) để giám sát và mở trang review.
    """
    from playwright.sync_api import sync_playwright

    chrome_exe = get_chrome_path()
    port = find_free_port()

    cmd = [
        chrome_exe,
        f"--user-data-dir={user_data_dir}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check"
    ]

    if proxy_config and proxy_config.get("server"):
        clean_server = proxy_config["server"].replace("http://", "").replace("https://", "")
        cmd.append(f"--proxy-server=http://{clean_server}")

    cmd.append(target_url)

    print(f"[Poster Native] Launching native Chrome at port {port} for target: {target_url}...")
    proc = subprocess.Popen(cmd)
    time.sleep(2)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            # Giữ trình duyệt mở cho người dùng tự do thao tác dán bài và đăng (Thoát ngay khi người dùng đóng Chrome)
            for _ in range(600):
                time.sleep(1)
                try:
                    if proc.poll() is not None or page.is_closed() or not context.pages:
                        print("[Poster Native] Chrome window closed by user.")
                        break
                    page.title()
                except Exception:
                    print("[Poster Native] Detected browser close. Exiting loop.")
                    break

            try:
                browser.close()
            except Exception:
                pass

        except Exception as cdp_err:
            print(f"[Poster Native Error] CDP connection error: {cdp_err}")

    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    return False


async def auto_post_review(
    db,
    user_email: str,
    business_name: str,
    place_id: str,
    url: str,
    rating: int,
    content: str,
    address: str = None,
    gmail: str = "reviewer.alpha01@gmail.com",
    proxy_str: str = None,
    images: list[str] = None,
    headless: bool = False
) -> dict:
    """
    Dịch vụ mở trình duyệt trực quan trên Google Search & tự động kích hoạt Popup 'Viết bài đánh giá'.
    """
    target_rating = int(rating) if rating else 5
    
    # Trích xuất Feature ID (0x...:0x...) từ URL hoặc place_id để tạo hashtag #lrd mở trực tiếp Popup trên Google Search
    feature_id_match = None
    if url:
        m = re.search(r'(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
        if m:
            feature_id_match = m.group(1)
    if not feature_id_match and place_id:
        m = re.search(r'(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', place_id)
        if m:
            feature_id_match = m.group(1)

    # Đính kèm địa chỉ/thành phố vào từ khóa tìm kiếm để Google Search từ Proxy địa phương khác khớp đúng Knowledge Panel
    search_query = business_name.strip()
    if address:
        parts = [p.strip() for p in address.split(",") if p.strip()]
        if parts:
            search_query = f"{search_query} {parts[-1]}"

    encoded_query = urllib.parse.quote(search_query)
    
    if feature_id_match:
        target_url = f"https://www.google.com/search?q={encoded_query}&hl=vi&gl=vn#lrd={feature_id_match},3,,,,"
    elif place_id and place_id.startswith("ChIJ") and len(place_id) > 25:
        target_url = f"https://search.google.com/local/writereview?placeid={place_id}"
    else:
        target_url = f"https://www.google.com/search?q={encoded_query}&hl=vi&gl=vn"

    fallback_url = url if url and url.startswith("http") else None

    await log_system_activity(
        db,
        "Khởi chạy mở Google Search Popup đánh giá",
        f"Bắt đầu quy trình mở Google Search cho '{business_name}' - Gmail: {gmail} - Proxy: {proxy_str or 'Direct'}",
        "info"
    )

    # Tra cứu Proxy từ CSDL hoặc bóc tách từ chuỗi truyền vào (bất kỳ định dạng IP:Port hoặc IP:Port:User:Pass)
    from app.services.proxy_utils import parse_proxy_config, get_proxy_config_for_gmail
    proxy_config = await get_proxy_config_for_gmail(db, gmail)
    if not proxy_config and proxy_str:
        proxy_config = parse_proxy_config(proxy_str)

    print(f"[Poster] Gmail '{gmail}' initializing Chrome with proxy: {proxy_config}")

    user_data_dir = os.path.join(os.getcwd(), ".browser_profiles", gmail.replace("@", "_"))
    os.makedirs(user_data_dir, exist_ok=True)

    try:
        is_posted = await asyncio.to_thread(
            _playwright_sync_post,
            user_data_dir,
            proxy_config,
            target_url,
            fallback_url,
            target_rating,
            content,
            images,
            headless
        )

        if is_posted:
            await log_system_activity(
                db,
                "Đăng bài review thành công",
                f"Đã phát hiện bài review cho '{business_name}' (Gmail: {gmail}) được ĐĂNG THÀNH CÔNG trên Google Maps!",
                "success"
            )

            return {
                "success": True,
                "posted": True,
                "message": f"Bài review cho {business_name} đã được đăng thành công trên Google Maps!"
            }

        await log_system_activity(
            db,
            "Mở Google Search & Popup đánh giá thành công",
            f"Đã mở Google Search và Popup đánh giá cho '{business_name}' (Gmail: {gmail}). Chờ người dùng tự điền & bấm Đăng.",
            "info"
        )

        return {
            "success": True,
            "posted": False,
            "message": f"Đã mở Google Search và Popup đánh giá cho {business_name}. Bạn hãy tự chọn số sao, dán nội dung và bấm Đăng trên Chrome."
        }

    except Exception as exec_err:
        print(f"[Poster Error] Failed automated posting task: {exec_err}")
        await log_system_activity(
            db,
            "Đăng review trực quan thất bại",
            f"Lỗi khi tự động chạy cho '{business_name}': {str(exec_err)}",
            "error"
        )
        return {
            "success": False,
            "message": f"Đăng review thất bại: {str(exec_err)}"
        }


