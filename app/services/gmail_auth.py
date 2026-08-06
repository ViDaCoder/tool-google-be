import os
import sys
import re
import time
import shutil
import asyncio
import subprocess
from urllib.parse import urlparse
from app.services.logs import log_system_activity

def get_chrome_path() -> str:
    """Tìm đường dẫn thực thi Google Chrome chính thức trên Windows."""
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return "chrome.exe"

def find_free_port() -> int:
    """Tìm cổng TCP rảnh để kết nối CDP tránh xung đột cổng 9222."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]
    except Exception:
        return 9222

def _is_post_login_page(url: str) -> bool:
    """Kiểm tra chắc chắn xem người dùng đã vượt qua bước gõ Mật khẩu & OTP để vào trang sau đăng nhập chưa."""
    if not url:
        return False
    url_lower = url.lower()
    # Nếu URL vẫn còn nằm ở trang đăng nhập, điền email, mật khẩu hoặc 2FA -> Chưa đăng nhập xong
    login_keywords = ["servicelogin", "signin", "identifier", "challenge", "pwd", "denied", "v3/signin"]
    if any(kw in url_lower for kw in login_keywords):
        return False
    # Kiểm tra URL đã chính thức chuyển hướng tới các trang quản lý tài khoản thành công
    post_keywords = ["myaccount.google.com", "mail.google.com", "google.com/search", "authuser"]
    return any(kw in url_lower for kw in post_keywords)


def _extract_email_from_page(page) -> str | None:
    """Bóc tách nhanh địa chỉ Gmail từ trang hiện tại trên Chrome qua Javascript & DOM attributes."""
    try:
        email = page.evaluate("""
            () => {
                // 1. Quét tất cả các phần tử có chứa attribute aria-label, title, alt, data-email, innerText
                const allEls = document.querySelectorAll('*');
                for (const el of allEls) {
                    const text = (el.getAttribute('aria-label') || '') + ' ' + 
                                 (el.getAttribute('title') || '') + ' ' + 
                                 (el.getAttribute('alt') || '') + ' ' + 
                                 (el.getAttribute('data-email') || '');
                    const match = text.match(/[a-zA-Z0-9._%+-]+@gmail\\.com/i);
                    if (match) {
                        const em = match[0].toLowerCase();
                        if (!em.includes('support') && !em.includes('google') && !em.includes('example') && !em.includes('privacy')) {
                            return em;
                        }
                    }
                }
                // 2. Quét thẻ a hoặc div tài khoản
                const links = document.querySelectorAll('a[href*="accounts.google.com"], a[href*="myaccount.google.com"]');
                for (const a of links) {
                    const text = a.href + ' ' + (a.innerText || '') + ' ' + (a.getAttribute('aria-label') || '');
                    const match = text.match(/[a-zA-Z0-9._%+-]+@gmail\\.com/i);
                    if (match) return match[0].toLowerCase();
                }
                // 3. Quét toàn bộ innerText
                const bodyText = document.body ? document.body.innerText : '';
                const bodyMatch = bodyText.match(/[a-zA-Z0-9._%+-]+@gmail\\.com/i);
                if (bodyMatch) {
                    const em = bodyMatch[0].toLowerCase();
                    if (!em.includes('support') && !em.includes('google') && !em.includes('example') && !em.includes('privacy')) {
                        return em;
                    }
                }
                return null;
            }
        """)
        if email:
            return email.strip().lower()
    except Exception:
        pass
    return None


def _sync_open_interactive_login() -> dict:
    """
    Khởi chạy Google Chrome nguyên bản bằng subprocess (không qua Playwright launch wrapper)
    để Google nhận diện 100% là ứng dụng Chrome chính chủ của Windows, giúp người dùng đăng nhập mượt mà.
    Playwright kết nối qua Remote Debugging Port (CDP) để tự động bóc tách Email & lưu Session Profile.
    """
    from playwright.sync_api import sync_playwright

    profiles_base = os.path.join(os.getcwd(), ".browser_profiles")
    os.makedirs(profiles_base, exist_ok=True)

    # Dọn dẹp triệt để tất cả các thư mục tạm cũ
    for item in os.listdir(profiles_base):
        if item.startswith("temp_new_login"):
            try:
                shutil.rmtree(os.path.join(profiles_base, item), ignore_errors=True)
            except Exception:
                pass

    # Tạo thư mục profile tạm hoàn toàn mới 100%
    temp_profile_dir = os.path.join(profiles_base, f"temp_new_login_{int(time.time())}")
    os.makedirs(temp_profile_dir, exist_ok=True)

    chrome_exe = get_chrome_path()
    port = 9222

    cmd = [
        chrome_exe,
        f"--user-data-dir={temp_profile_dir}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://accounts.google.com/ServiceLogin"
    ]

    print(f"[GmailAuth Native] Launching native Chrome at port {port} with clean temp profile: {temp_profile_dir}...")
    proc = subprocess.Popen(cmd)
    time.sleep(2)

    detected_email = None

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            # Lắng nghe người dùng đăng nhập (Không giới hạn thời gian chờ ngắt kết nối)
            for step in range(3600):
                if proc.poll() is not None:
                    print("[GmailAuth Native] Chrome process exited by user.")
                    break
                time.sleep(1)
                try:
                    if page.is_closed() or not context.pages:
                        print("[GmailAuth Native] Chrome window closed by user.")
                        break

                    current_url = page.url
                    em = _extract_email_from_page(page)

                    if _is_post_login_page(current_url):
                        if em:
                            detected_email = em
                        else:
                            try:
                                bg_page = context.new_page()
                                bg_page.goto("https://myaccount.google.com/email", wait_until="domcontentloaded", timeout=5000)
                                time.sleep(1)
                                bg_em = _extract_email_from_page(bg_page)
                                bg_page.close()
                                if bg_em:
                                    detected_email = bg_em
                            except Exception as bg_err:
                                print(f"[GmailAuth Native] Background email extraction sub-step error: {bg_err}")

                        if detected_email:
                            print(f"[GmailAuth Native] Successfully detected login for {detected_email}. Keeping Chrome open up to 120s for full session data collection...")
                            for wait_sec in range(120):
                                time.sleep(1)
                                if proc.poll() is not None or not context.pages or (context.pages and page.is_closed()):
                                    print("[GmailAuth Native] Chrome window closed by user after login.")
                                    break
                            break
                except Exception as loop_err:
                    print(f"[GmailAuth Native] Chrome disconnected or closed: {loop_err}")
                    break

            try:
                browser.close()
            except Exception:
                pass

        except Exception as cdp_err:
            print(f"[GmailAuth Native Error] CDP connection error: {cdp_err}")

    # Đóng tiến trình Chrome sau khi hoàn tất
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    time.sleep(1)

    if detected_email:
        target_profile_dir = os.path.join(profiles_base, detected_email.replace("@", "_"))
        try:
            if os.path.exists(target_profile_dir):
                shutil.rmtree(target_profile_dir, ignore_errors=True)
            shutil.move(temp_profile_dir, target_profile_dir)
        except Exception as move_err:
            print(f"[GmailAuth Native] Move profile error: {move_err}, trying copytree...")
            try:
                shutil.copytree(temp_profile_dir, target_profile_dir, dirs_exist_ok=True)
                shutil.rmtree(temp_profile_dir, ignore_errors=True)
            except Exception:
                pass

        return {
            "success": True,
            "email": detected_email,
            "message": f"Đã đăng nhập và lưu thành công phiên Gmail: {detected_email}"
        }
    else:
        # Dọn dẹp thư mục tạm nếu người dùng hủy đăng nhập
        try:
            shutil.rmtree(temp_profile_dir, ignore_errors=True)
        except Exception:
            pass

        return {
            "success": False,
            "email": None,
            "message": "Chưa hoàn tất đăng nhập hoặc không phát hiện được địa chỉ Gmail."
        }


def _sync_interactive_gmail_login(user_data_dir: str, email: str, proxy_config: dict | None) -> dict:
    """
    Khởi chạy Google Chrome nguyên bản bằng subprocess cho tài khoản Gmail có sẵn để nạp lại phiên.
    Sử dụng Remote Debugging Port (CDP) động để đếm cookies & tự lưu session xuống đĩa.
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

    cmd.append("https://accounts.google.com/ServiceLogin")

    print(f"[GmailAuth Native Session] Launching native Chrome at port {port} for {email} (Proxy: {proxy_config.get('server') if proxy_config else 'Direct'})...")
    proc = subprocess.Popen(cmd)
    time.sleep(2)

    logged_in = False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            # Chờ người dùng thực hiện điền Mật khẩu và OTP (Không giới hạn thời gian chờ ngắt kết nối)
            for step in range(3600):
                time.sleep(1)
                try:
                    # Nếu người dùng chủ động tắt cửa sổ Chrome trước -> Kiểm tra trạng thái và thoát ngay lập tức
                    if proc.poll() is not None or (context.pages and page.is_closed()):
                        print(f"[GmailAuth Native Session] Chrome window closed by user for {email}.")
                        cookies = context.cookies()
                        has_google_sid = any(c.get("name") in ["SID", "HSID", "SSID"] and "google.com" in c.get("domain", "") for c in cookies)
                        if has_google_sid:
                            logged_in = True
                        break

                    cookies = context.cookies()
                    has_google_sid = any(c.get("name") in ["SID", "HSID", "SSID"] and "google.com" in c.get("domain", "") for c in cookies)

                    current_url = ""
                    if context.pages and not page.is_closed():
                        try:
                            current_url = page.url
                        except Exception:
                            pass

                    # Khi phát hiện đã đăng nhập thành công
                    if (has_google_sid or _is_post_login_page(current_url)) and not logged_in:
                        logged_in = True
                        print(f"[GmailAuth Native Session] Successfully detected login for {email}. Keeping window open up to 120s for full page load...")
                        
                        # Giữ trình duyệt mở tối đa 120 giây (2 phút) cho trang tải xong 100% & cào đủ dữ liệu.
                        # Nếu người dùng bấm X đóng Chrome trước 2 phút -> Thoát ngay lập tức không bắt chờ!
                        for wait_sec in range(120):
                            time.sleep(1)
                            if proc.poll() is not None or not context.pages or (context.pages and page.is_closed()):
                                print(f"[GmailAuth Native Session] User closed Chrome window naturally after {wait_sec + 1}s.")
                                break
                        break
                except Exception as loop_err:
                    print(f"[GmailAuth Native Session Warning] Loop check warning: {loop_err}")
                    break

            try:
                browser.close()
            except Exception:
                pass

        except Exception as cdp_err:
            print(f"[GmailAuth Native Session Error] CDP connection error: {cdp_err}")

    # Đóng tiến trình Chrome êm đẹp (Graceful shutdown) để ghi toàn bộ dữ liệu SQLite Cookies vào Profile
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    time.sleep(1)

    if logged_in:
        return {
            "success": True,
            "status": "Hoạt động",
            "message": f"Đã nạp thành công phiên Gmail cho tài khoản {email}"
        }
    else:
        return {
            "success": False,
            "status": "Cần xác minh",
            "message": f"Chưa hoàn tất đăng nhập phiên Gmail cho tài khoản {email}"
        }


async def open_interactive_login_service(db) -> dict:
    """
    Dịch vụ mở cửa sổ Chrome cho người dùng tự nhập Gmail mới.
    """
    await log_system_activity(
        db,
        "Mở cửa sổ thêm Gmail mới",
        "Đã mở cửa sổ Chrome cho người dùng tự nhập Email, Mật khẩu & OTP.",
        "info"
    )

    try:
        res = await asyncio.to_thread(_sync_open_interactive_login)
        if res.get("success") and res.get("email"):
            await log_system_activity(
                db,
                "Thêm Gmail thành công qua trình duyệt",
                f"Đã bắt thành công địa chỉ Gmail: {res['email']} và lưu Profile làm việc.",
                "success"
            )
        return res
    except Exception as err:
        print(f"[GmailAuth Error] Interactive login failed: {err}")
        return {
            "success": False,
            "email": None,
            "message": f"Lỗi khi mở cửa sổ đăng nhập: {str(err)}"
        }


async def init_gmail_session(
    db,
    email: str,
    raw_password: str = "",
    proxy_str: str = None
) -> dict:
    """
    Dịch vụ nạp lại phiên làm việc cho tài khoản Gmail có sẵn.
    """
    email_clean = email.strip().lower()
    user_data_dir = os.path.join(os.getcwd(), ".browser_profiles", email_clean.replace("@", "_"))
    os.makedirs(user_data_dir, exist_ok=True)

    from app.services.proxy_utils import parse_proxy_config, get_proxy_config_for_gmail
    proxy_config = await get_proxy_config_for_gmail(db, email_clean)
    if not proxy_config and proxy_str:
        proxy_config = parse_proxy_config(proxy_str)

    await log_system_activity(
        db,
        "Mở cửa sổ nạp phiên Gmail",
        f"Đã mở cửa sổ Chrome để nạp phiên Google cho tài khoản: {email_clean}",
        "info"
    )

    try:
        res = await asyncio.to_thread(
            _sync_interactive_gmail_login,
            user_data_dir,
            email_clean,
            proxy_config
        )

        await log_system_activity(
            db,
            "Lưu phiên Gmail thành công",
            f"Đã bắt và lưu thành công Profile Session cho tài khoản {email_clean}.",
            "success"
        )
        return res

    except Exception as err:
        print(f"[GmailAuth Error] Failed interactive session for {email_clean}: {err}")
        return {
            "success": False,
            "status": "Cần xác minh",
            "message": f"Lỗi khi mở cửa sổ đăng nhập: {str(err)}"
        }
