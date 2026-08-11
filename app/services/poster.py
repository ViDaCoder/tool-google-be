import os
import sys
import re
import time
import random
import glob
import subprocess
import asyncio
import urllib.parse
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
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


def to_unsigned_snake_case(text: str) -> str:
    if not text:
        return ""
    patterns = {
        '[àáạảãâầấậẩẫăằắặẳẵ]': 'a',
        '[èéẹẻẽêềếệểễ]': 'e',
        '[ìíịỉĩ]': 'i',
        '[òóọỏõôồốộổỗơờớợởỡ]': 'o',
        '[ùúụủũưừứựửữ]': 'u',
        '[ỳýỵỷỹ]': 'y',
        '[đ]': 'd',
        '[ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴ]': 'a',
        '[ÈÉẸẺẼÊỀẾỆỂỄ]': 'e',
        '[ÌÍỊỈĨ]': 'i',
        '[ÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ]': 'o',
        '[ÙÚỤỦŨƯỪỨỰỬỮ]': 'u',
        '[ỲÝỴỶỸ]': 'y',
        '[Đ]': 'd'
    }
    text = text.lower()
    for pattern, repl in patterns.items():
        text = re.sub(pattern, repl, text)
    
    # Thay thế các ký tự không phải chữ/số bằng khoảng trắng, sau đó gom thành dấu gạch dưới
    text = re.sub(r'[^a-z0-9\s_]', ' ', text)
    text = re.sub(r'\s+', '_', text.strip())
    text = re.sub(r'_+', '_', text)
    return text


def inject_red_cursor_helper(page):
    try:
        page.evaluate("""() => {
            if (document.getElementById('playwright-red-cursor')) return;
            const box = document.createElement('div');
            box.id = 'playwright-red-cursor';
            box.style.position = 'fixed';
            box.style.width = '14px';
            box.style.height = '14px';
            box.style.borderRadius = '50%';
            box.style.background = 'red';
            box.style.border = '2px solid white';
            box.style.boxShadow = '0 0 8px rgba(0,0,0,0.5)';
            box.style.pointerEvents = 'none';
            box.style.zIndex = '99999999';
            box.style.left = '-100px';
            box.style.top = '-100px';
            box.style.transition = 'left 0.03s linear, top 0.03s linear';
            document.body.appendChild(box);
            
            // Định nghĩa hàm cập nhật tọa độ độc lập gọi từ Python
            window.updatePlaywrightCursor = (x, y) => {
                box.style.left = x - 7 + 'px';
                box.style.top = y - 7 + 'px';
            };
        }""")
        print("[Poster Native] Injected red cursor visual feedback helper successfully.")
    except Exception as e:
        print(f"[Poster Native Warning] Failed to inject red cursor helper: {e}")


def smooth_move_mouse_with_cursor(page, target_x, target_y, steps=65):
    import math
    import random
    try:
        # Khởi tạo tọa độ ngẫu nhiên ban đầu hoặc lấy vị trí cũ của chấm đỏ từ DOM
        start_x = random.randint(150, 850)
        start_y = random.randint(150, 650)
        try:
            current_pos = page.evaluate("""() => {
                const box = document.getElementById('playwright-red-cursor');
                if (box && box.style.left !== '-100px') {
                    return { x: parseFloat(box.style.left) + 7, y: parseFloat(box.style.top) + 7 };
                }
                return null;
            }""")
            if current_pos and current_pos['x'] > 0 and current_pos['y'] > 0:
                start_x, start_y = current_pos['x'], current_pos['y']
        except Exception:
            pass

        # Tính toán đường cong Bezier bậc 2 để tạo nét lướt chuột cong võng tự nhiên
        mid_x = (start_x + target_x) / 2
        mid_y = (start_y + target_y) / 2
        
        dx = target_x - start_x
        dy = target_y - start_y
        distance = math.sqrt(dx*dx + dy*dy)
        
        # Chọn ngẫu nhiên loại quỹ đạo di chuyển (chữ C, chữ S hoặc lượn sóng)
        curve_type = "quadratic"
        if distance > 30:
            curve_type = random.choice(["quadratic", "cubic", "wavy"])
            
        # Chuẩn bị các tham số cho từng loại quỹ đạo
        if distance > 10:
            px = -dy
            py = dx
            nx = px / distance
            ny = py / distance
            
            if curve_type == "quadratic":
                # Điểm uốn cho đường cong Bézier bậc 2 (chữ C)
                deviation = random.choice([-1, 1]) * random.randint(40, min(120, int(distance * 0.4) + 10))
                ctrl_x = mid_x + nx * deviation
                ctrl_y = mid_y + ny * deviation
            elif curve_type == "cubic":
                # 2 Điểm uốn đối xứng cho đường cong Bézier bậc 3 (chữ S)
                pt1_x = start_x + dx * 0.33
                pt1_y = start_y + dy * 0.33
                pt2_x = start_x + dx * 0.66
                pt2_y = start_y + dy * 0.66
                
                dev1 = random.randint(30, min(100, int(distance * 0.3) + 10))
                dev2 = random.randint(30, min(100, int(distance * 0.3) + 10))
                side = random.choice([-1, 1])
                
                ctrl1_x = pt1_x + nx * (side * dev1)
                ctrl1_y = pt1_y + ny * (side * dev1)
                ctrl2_x = pt2_x + nx * (-side * dev2)
                ctrl2_y = pt2_y + ny * (-side * dev2)
            else:
                # Đường lượn sóng sine
                cycles = random.choice([1, 2])
                wave_amplitude = random.randint(10, 25)
        else:
            ctrl_x = mid_x
            ctrl_y = mid_y

        # Thực hiện trượt chuột ảo và cập nhật chấm đỏ theo quỹ đạo đã chọn
        for i in range(1, steps + 1):
            progress = i / steps
            
            # 1. Hàm Easing Cubic Ease-In-Out (Nhanh dần ở giữa, chậm dần ở 2 đầu đặc biệt là khi tới đích)
            if progress < 0.5:
                t = 4 * progress**3
            else:
                t = 1 - (-2 * progress + 2)**3 / 2
                
            # 2. Rung tay vật lý ngẫu nhiên (Jitter) - giảm dần biên độ khi chuột tiến sát vào tâm mục tiêu
            jitter_scale = (1 - t) * 1.8  # Biên độ rung tối đa 1.8 pixel
            jitter_x = random.uniform(-jitter_scale, jitter_scale)
            jitter_y = random.uniform(-jitter_scale, jitter_scale)
            
            # 3. Tính toán tọa độ dựa trên quỹ đạo di chuyển được chọn
            if curve_type == "quadratic" or distance <= 10:
                # Công thức Bézier bậc 2 (chữ C)
                curr_x = (1 - t)**2 * start_x + 2 * (1 - t) * t * ctrl_x + t**2 * target_x + jitter_x
                curr_y = (1 - t)**2 * start_y + 2 * (1 - t) * t * ctrl_y + t**2 * target_y + jitter_y
            elif curve_type == "cubic":
                # Công thức Bézier bậc 3 (chữ S)
                curr_x = (1 - t)**3 * start_x + 3 * (1 - t)**2 * t * ctrl1_x + 3 * (1 - t) * t**2 * ctrl2_x + t**3 * target_x + jitter_x
                curr_y = (1 - t)**3 * start_y + 3 * (1 - t)**2 * t * ctrl1_y + 3 * (1 - t) * t**2 * ctrl2_y + t**3 * target_y + jitter_y
            else:
                # Công thức lượn sóng Sine
                base_x = (1 - t) * start_x + t * target_x
                base_y = (1 - t) * start_y + t * target_y
                wave_offset = math.sin(t * math.pi * cycles) * wave_amplitude * (1 - t) # Biên độ giảm dần khi tới gần đích
                curr_x = base_x + nx * wave_offset + jitter_x
                curr_y = base_y + ny * wave_offset + jitter_y
            
            # 4. Di chuyển con trỏ chuột ảo của Playwright
            page.mouse.move(curr_x, curr_y)
            
            # 5. Đồng bộ hóa trực tiếp chấm đỏ
            try:
                page.evaluate(f"if (window.updatePlaywrightCursor) window.updatePlaywrightCursor({curr_x}, {curr_y});")
            except Exception:
                pass
                
            # 6. Biến thiên thời gian trễ ngẫu nhiên (Sleep Variation) mô phỏng tốc độ biến thiên thực tế
            base_sleep = 0.015
            if progress < 0.15 or progress > 0.85:
                base_sleep = 0.022
            sleep_time = base_sleep + random.uniform(-0.003, 0.003)
            time.sleep(max(0.005, sleep_time))
    except Exception as e:
        print(f"[Poster Native Warning] Smooth Bezier mouse move failed: {e}")
        page.mouse.move(target_x, target_y)


def find_upload_button(target_root):
    # Các selector thử nghiệm theo thứ tự ưu tiên
    candidates = [
        'text=Thêm ảnh và video',
        'text=Thêm hình',
        'text=Add photos',
        'text=Add photos and video',
        'button:has-text("Thêm ảnh và video")',
        'button:has-text("Thêm hình")',
        'button:has-text("Add photos")',
        '[role="button"]:has-text("Thêm ảnh")',
        '[role="button"]:has-text("Thêm hình")',
        '[role="button"]:has-text("Add photos")',
        '[aria-label="Thêm ảnh và video"]',
        '[aria-label="Thêm hình"]',
        '[aria-label="Add photos and video"]',
        '[aria-label="Add photos"]'
    ]
    for sel in candidates:
        try:
            btn = target_root.locator(sel).first
            if btn.is_visible():
                return btn, sel
        except Exception:
            pass
    return None, None


def _playwright_sync_post(
    user_data_dir: str,
    proxy_config: dict | None,
    target_url: str,
    fallback_url: str | None,
    target_rating: int,
    content: str,
    images: list[str] = None,
    headless: bool = False,
    business_name: str = "",
    auto_submit: bool = False
) -> bool:
    """
    Khởi chạy Google Chrome nguyên bản bằng subprocess cho tài khoản Gmail có sẵn để đăng bài.
    Sử dụng chung 100% Profile & cấu hình với chức năng Nạp phiên giúp giữ trạng thái ĐÃ ĐĂNG NHẬP.
    Playwright kết nối ngầm qua Remote Debugging Port (CDP) để giám sát và mở trang review.
    """
    import subprocess as _subprocess
    chrome_exe = get_chrome_path()
    port = find_free_port()

    # Xây dựng lệnh khởi chạy Chrome THẬT (giống hệt cách Nạp phiên trong gmail_auth.py)
    cmd = [
        chrome_exe,
        f"--user-data-dir={user_data_dir}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-infobars",
    ]

    if headless:
        cmd.append("--headless=new")

    # Cấu hình Proxy qua flag của Chrome (không qua Playwright proxy param)
    if proxy_config and proxy_config.get("server"):
        clean_server = proxy_config["server"].replace("http://", "").replace("https://", "")
        cmd.append(f"--proxy-server=http://{clean_server}")

    # Mở thẳng tới trang đích ngay từ đầu
    cmd.append(target_url)

    print(f"[Poster Native CDP] Launching native Chrome at port {port} for target: {target_url} (Proxy: {proxy_config.get('server') if proxy_config else 'Direct'})...")
    proc = _subprocess.Popen(cmd)
    time.sleep(2)  # Chờ Chrome khởi động

    with sync_playwright() as p:
        browser = None
        try:
            # Kết nối qua CDP - giống hệt cách Nạp phiên
            for attempt in range(10):
                try:
                    browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
                    print(f"[Poster Native CDP] Connected to Chrome via CDP on port {port} (attempt {attempt + 1})")
                    break
                except Exception as cdp_err:
                    print(f"[Poster Native CDP] CDP connection attempt {attempt + 1} failed: {cdp_err}")
                    time.sleep(1)

            if not browser:
                raise Exception(f"Cannot connect to Chrome via CDP on port {port} after 10 attempts.")

            context = browser.contexts[0]

            # Lấy page đang ở target_url hoặc mở tab mới
            page = None
            for pg in context.pages:
                if target_url[:30] in pg.url or pg.url in ("about:blank", ""):
                    page = pg
                    break
            if page is None:
                page = context.new_page()

            # Tự động xác thực Proxy qua CDP Fetch API (tránh Chrome hiện dialog Sign in thủ công)
            # Cần thiết khi proxy có username/password và Chrome được mở bằng subprocess (không qua Playwright proxy param)
            cdp_session = None
            if proxy_config and proxy_config.get("username") and proxy_config.get("password"):
                try:
                    cdp_session = context.new_cdp_session(page)
                    cdp_session.send("Fetch.enable", {
                        "handleAuthRequests": True,
                        "patterns": [{"urlPattern": "*"}]
                    })

                    proxy_user = proxy_config.get("username", "")
                    proxy_pass = proxy_config.get("password", "")

                    def on_auth_required(event):
                        try:
                            request_id = event["requestId"]
                            cdp_session.send("Fetch.continueWithAuth", {
                                "requestId": request_id,
                                "authChallengeResponse": {
                                    "response": "ProvideCredentials",
                                    "username": proxy_user,
                                    "password": proxy_pass
                                }
                            })
                            print(f"[Poster Native CDP] Auto-filled proxy auth for requestId: {request_id}")
                        except Exception as auth_err:
                            print(f"[Poster Native CDP] Proxy auth fill error: {auth_err}")

                    def on_request_paused(event):
                        try:
                            request_id = event["requestId"]
                            cdp_session.send("Fetch.continueRequest", {"requestId": request_id})
                        except Exception:
                            pass

                    cdp_session.on("Fetch.authRequired", on_auth_required)
                    cdp_session.on("Fetch.requestPaused", on_request_paused)
                    print(f"[Poster Native CDP] Proxy auth interception enabled for user: {proxy_user}")
                except Exception as proxy_auth_err:
                    print(f"[Poster Native CDP] Could not set up proxy auth interception: {proxy_auth_err}")

            # Điều hướng nếu tab chưa ở đúng URL
            try:
                if page.url != target_url and not page.url.startswith("https://www.google.com/search"):
                    print(f"[Poster Native CDP] Navigating to target URL: {target_url}")
                    page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                else:
                    print(f"[Poster Native CDP] Already on target page: {page.url}")
            except Exception as nav_err:
                print(f"[Poster Native CDP] Initial navigation warning: {nav_err}")

            # Tắt cờ Fetch.enable ngay sau khi nạp xong trang để giải phóng cờ DevTools Interception trước khi điền form
            if cdp_session:
                try:
                    time.sleep(1)
                    cdp_session.send("Fetch.disable")
                    print("[Poster Native CDP] Disabled Fetch interception after page load successfully.")
                except Exception as disable_err:
                    print(f"[Poster Native CDP] Warning disabling Fetch interception: {disable_err}")


            # Đăng ký tự động tiêm con trỏ chuột màu đỏ khi điều hướng trang (Hỗ trợ cả trong và ngoài iframe)
            try:
                page.add_init_script("""() => {
                    const drawCursor = () => {
                        if (document.getElementById('playwright-red-cursor')) return;
                        const box = document.createElement('div');
                        box.id = 'playwright-red-cursor';
                        box.style.position = 'fixed';
                        box.style.width = '14px';
                        box.style.height = '14px';
                        box.style.borderRadius = '50%';
                        box.style.background = 'red';
                        box.style.border = '2px solid white';
                        box.style.boxShadow = '0 0 8px rgba(0,0,0,0.5)';
                        box.style.pointerEvents = 'none';
                        box.style.zIndex = '99999999';
                        box.style.left = '-100px';
                        box.style.top = '-100px';
                        box.style.transition = 'left 0.05s linear, top 0.05s linear';
                        document.body.appendChild(box);
                        
                        window.addEventListener('mousemove', (e) => {
                            box.style.left = e.clientX - 7 + 'px';
                            box.style.top = e.clientY - 7 + 'px';
                        }, true);
                    };
                    if (document.readyState === 'loading') {
                        document.addEventListener('DOMContentLoaded', drawCursor);
                    } else {
                        drawCursor();
                    }
                }""")
                inject_red_cursor_helper(page)
            except Exception as init_err:
                print(f"[Poster Native Warning] Failed to add init script for red cursor: {init_err}")

            # --- XÁC ĐỊNH CONTEXT CỦA POPUP (PAGE HOẶC IFRAME) ---
            target_root = page
            iframe_selector = 'iframe[name="goog-reviews-write-widget"], iframe.goog-reviews-write-widget'
            dialog_selector = '[role="dialog"], g-dialog-content, .g-dialog-content'
            
            print("[Poster Native] Waiting for review form context to be ready...")
            try:
                # Đợi cho trang load xong DOM (tối đa 45 giây do Proxy có thể rất chậm)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=45000)
                except Exception:
                    pass
                
                found_context = False
                # Chờ tối đa 30 giây để tìm thấy bất kỳ Iframe hoặc Dialog popup review xuất hiện
                for check_sec in range(30):
                    # 1. Kiểm tra xem iframe review có hiển thị chưa
                    iframe_el = page.locator(iframe_selector).first
                    if iframe_el.is_visible():
                        print(f"[Poster Native] Found review iframe after {check_sec}s.")
                        target_root = page.frame_locator(iframe_selector)
                        found_context = True
                        break
                    
                    # 2. Kiểm tra xem popup dialog trực tiếp trên trang chính đã xuất hiện chưa
                    dialog_el = page.locator(dialog_selector).first
                    if dialog_el.is_visible():
                        print(f"[Poster Native] Found review popup dialog directly on page after {check_sec}s.")
                        target_root = dialog_el
                        found_context = True
                        break
                    
                    time.sleep(1)
                
                # Để popup/iframe hiển thị đầy đủ và ổn định (1.5 giây) như khách hàng yêu cầu
                time.sleep(1.5)
                print("[Poster Native] Settle time of 1.5s completed.")
                
            except Exception as wait_err:
                print(f"[Poster Native Warning] Error during review form visibility wait: {wait_err}")

            # --- TẮT TOOLTIP HƯỚNG DẪN CỦA GOOGLE NẾU CÓ ---
            try:
                page.bring_to_front()
                popup_box = None
                
                # Tìm bounding box của dialog trước
                for sel in ['g-dialog-content', '[role="dialog"]', '.g-dialog-content']:
                    el = page.locator(sel).first
                    if el.is_visible():
                        popup_box = el.bounding_box()
                        break
                
                # Nếu không thấy dialog, tìm bounding box của iframe
                if not popup_box:
                    iframe_el = page.locator(iframe_selector).first
                    if iframe_el.is_visible():
                        popup_box = iframe_el.bounding_box()
                        
                if popup_box:
                    # Tọa độ nhấp ngẫu nhiên một chút trong khu vực tiêu đề trống của dialog
                    tx = popup_box["x"] + random.uniform(40, 80)
                    ty = popup_box["y"] + random.uniform(20, 45)
                    print(f"[Poster Native] Clicking popup empty space at ({tx}, {ty}) to dismiss Google tooltip...")
                    smooth_move_mouse_with_cursor(page, tx, ty)
                    time.sleep(random.uniform(0.8, 1.5))
                    page.mouse.click(tx, ty)
                    time.sleep(random.uniform(0.8, 1.5))
            except Exception as tooltip_err:
                print(f"[Poster Native Warning] Failed to click title to dismiss tooltip: {tooltip_err}")

            # --- PHẦN TỰ ĐỘNG HÓA TẢI HÌNH ẢNH LÊN ---
            # Sử dụng trực tiếp danh sách ảnh đã được lọc và phân bổ truyền từ ngoài vào
            image_paths = list(set([os.path.abspath(p) for p in images])) if images else []
            print(f"[Poster Native] Allocated images to upload: {image_paths}")

            if image_paths:
                # Định nghĩa các selector cho nút "Thêm ảnh và video" / "Thêm hình" (Chỉ nhắm mục tiêu button và role button để tránh match div cha)
                upload_selectors = [
                    'text=Thêm ảnh và video',
                    'text=Thêm hình',
                    'text=Add photos',
                    'text=Add photos and video',
                    'button:has-text("Thêm ảnh và video")',
                    'button:has-text("Thêm hình")',
                    'button:has-text("Add photos")',
                    '[role="button"]:has-text("Thêm ảnh và video")',
                    '[role="button"]:has-text("Thêm hình")',
                    '[role="button"]:has-text("Add photos")',
                    '[aria-label="Thêm ảnh và video"]',
                    '[aria-label="Thêm hình"]',
                    '[aria-label="Add photos and video"]',
                    '[aria-label="Add photos"]'
                ]
                upload_selector = ", ".join(upload_selectors)
                
                try:
                    # Tìm nút upload trong target_root đã được xác định ở trên
                    upload_btn, matched_sel = find_upload_button(target_root)
                    
                    # --- THỰC HIỆN TẢI HÌNH ẢNH LÊN ---
                    # Chỉ quét tìm input[type="file"] nằm bên trong target_root (tránh quét Google Lens ở ngoài)
                    file_input = target_root.locator('input[type="file"]').first
                    direct_success = False
                    try:
                        # Đợi xem input file có sẵn trong DOM của target_root không
                        file_input.wait_for(state="attached", timeout=3000)
                        print(f"[Poster Native] Found input[type='file'] inside review popup context. Uploading {len(image_paths)} images directly...")
                        file_input.set_input_files(image_paths)
                        print("[Poster Native] Direct input upload finished successfully.")
                        direct_success = True
                    except Exception as direct_err:
                        print(f"[Poster Native] Direct input upload not available or timed out: {direct_err}. Falling back to click method...")
                        
                    if not direct_success:
                        # Cách 2: Giả lập click chuột vật lý và bắt File Chooser
                        # Đảm bảo trang được đưa lên trước và focus
                        page.bring_to_front()
                        
                        # Nếu chưa có upload_btn thì quét tìm lại
                        if not upload_btn:
                            upload_btn, matched_sel = find_upload_button(target_root)
                            
                        if not upload_btn:
                            print("[Poster Native Error] Upload button not found in review popup context. Skipping click fallback.")
                            raise Exception("Upload button not found")
                            
                        upload_btn.wait_for(state="visible", timeout=15000)
                        box = upload_btn.bounding_box()
                        
                        # Sử dụng cơ chế expect_file_chooser của Playwright để bắt sự kiện chọn file khi click nút
                        print("[Poster Native] Clicking 'Thêm ảnh và video' button and expecting file chooser...")
                        if box:
                            # Nhấp ngẫu nhiên lệch trung tâm từ 25% đến 75% diện tích nút
                            x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
                            y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
                            print(f"[Poster Native] Sliding mouse smoothly to absolute coordinates ({x}, {y}) and clicking...")
                            
                            # Trượt chuột ảo mượt mà và cập nhật chấm đỏ độc lập
                            smooth_move_mouse_with_cursor(page, x, y)
                            time.sleep(random.uniform(1.0, 2.0)) # Nghỉ ngẫu nhiên 1-2s trước khi click
                            
                            with page.expect_file_chooser() as fc_info:
                                page.mouse.click(x, y)
                        else:
                            print("[Poster Native] Bounding box not found. Falling back to standard click...")
                            with page.expect_file_chooser() as fc_info:
                                upload_btn.click(force=True)
                        
                        file_chooser = fc_info.value
                        print(f"[Poster Native] File chooser intercepted. Uploading {len(image_paths)} images...")
                        file_chooser.set_files(image_paths)
                        print("[Poster Native] Finished upload sequence successfully.")
                        time.sleep(random.uniform(1.0, 2.0)) # Nghỉ ngẫu nhiên 1-2s sau khi upload xong
                except Exception as upload_err:
                    print(f"[Poster Native Warning] Automated image upload failed/skipped: {upload_err}")
            else:
                print("[Poster Native] No images to upload, skipping upload sequence.")
            # ----------------------------------------
            # --- TỰ ĐỘNG CHỌN SỐ SAO VÀ NHẬP NỘI DUNG ---
            try:
                # 1. Chọn số sao
                print(f"[Poster Native] Selecting star rating: {target_rating} stars...")
                star_elements = target_root.locator('[role="radio"]').all()
                if len(star_elements) >= 5:
                    num_groups = len(star_elements) // 5
                    print(f"[Poster Native] Found {len(star_elements)} star radio buttons, grouped into {num_groups} rating rows.")
                    
                    # Click nhóm sao chính đầu tiên (chỉ số 0 đến 4)
                    star_idx = min(max(int(target_rating), 1), 5) - 1
                    target_star = star_elements[star_idx]
                    box_star = target_star.bounding_box()
                    if box_star:
                        # Click lệch ngẫu nhiên 25% - 75% trên bề mặt ngôi sao chính
                        sx = box_star["x"] + box_star["width"] * random.uniform(0.25, 0.75)
                        sy = box_star["y"] + box_star["height"] * random.uniform(0.25, 0.75)
                        print(f"[Poster Native] Sliding mouse to main star {target_rating} at ({sx}, {sy}) and clicking...")
                        smooth_move_mouse_with_cursor(page, sx, sy)
                        time.sleep(random.uniform(1.0, 2.0)) # Nghỉ ngẫu nhiên 1-2s trước khi click chọn sao
                        page.mouse.click(sx, sy)
                        time.sleep(random.uniform(1.0, 2.0)) # Nghỉ ngẫu nhiên 1-2s sau khi chọn sao
                    else:
                        target_star.click(force=True)
                        time.sleep(random.uniform(1.0, 2.0))

                    # Click các nhóm sao phụ (Đồ ăn, Dịch vụ, Bầu không khí...) nếu có
                    for group_idx in range(1, num_groups):
                        sub_star_idx = group_idx * 5 + star_idx
                        if sub_star_idx < len(star_elements):
                            sub_star = star_elements[sub_star_idx]
                            box_sub = sub_star.bounding_box()
                            if box_sub:
                                # Click lệch ngẫu nhiên 25% - 75% trên bề mặt ngôi sao phụ
                                sx = box_sub["x"] + box_sub["width"] * random.uniform(0.25, 0.75)
                                sy = box_sub["y"] + box_sub["height"] * random.uniform(0.25, 0.75)
                                print(f"[Poster Native] Sliding mouse to sub-rating row {group_idx} star {target_rating} at ({sx}, {sy}) and clicking...")
                                smooth_move_mouse_with_cursor(page, sx, sy)
                                time.sleep(random.uniform(0.6, 1.2)) # Nghỉ ngẫu nhiên giữa các dòng
                                page.mouse.click(sx, sy)
                                time.sleep(random.uniform(0.6, 1.2))
                            else:
                                sub_star.click(force=True)
                                time.sleep(random.uniform(0.6, 1.2))
                else:
                    # Fallback bằng aria-label
                    fallback_star_selectors = [
                        f'[aria-label*="{target_rating} sao"]',
                        f'[aria-label*="{target_rating} star"]',
                        f'[aria-label*="Rate {target_rating}"]'
                    ]
                    for f_sel in fallback_star_selectors:
                        try:
                            star_el = target_root.locator(f_sel).first
                            if star_el.is_visible():
                                box_star = star_el.bounding_box()
                                if box_star:
                                    # Click lệch ngẫu nhiên trên bề mặt ngôi sao fallback
                                    sx = box_star["x"] + box_star["width"] * random.uniform(0.25, 0.75)
                                    sy = box_star["y"] + box_star["height"] * random.uniform(0.25, 0.75)
                                    smooth_move_mouse_with_cursor(page, sx, sy)
                                    time.sleep(random.uniform(1.0, 2.0))
                                    page.mouse.click(sx, sy)
                                else:
                                    star_el.click(force=True)
                                time.sleep(random.uniform(1.0, 2.0))
                                break
                        except Exception:
                            pass

                # 2. Nhập nội dung đánh giá
                if content:
                    print("[Poster Native] Locating review text input area...")
                    text_input = None
                    text_selectors = [
                        'textarea',
                        '[role="textbox"]',
                        'textarea[aria-label*="đánh giá"]',
                        'textarea[aria-label*="review"]'
                    ]
                    for ts in text_selectors:
                        try:
                            el = target_root.locator(ts).first
                            if el.is_visible():
                                text_input = el
                                print(f"[Poster Native] Found text input using selector: '{ts}'")
                                break
                        except Exception:
                            pass
                            
                    if text_input:
                        box_text = text_input.bounding_box()
                        if box_text:
                            # Điểm nhấp dao động ngẫu nhiên rộng rãi trên bề mặt của hộp Textarea nhập liệu
                            tx = box_text["x"] + box_text["width"] * random.uniform(0.25, 0.75)
                            ty = box_text["y"] + box_text["height"] * random.uniform(0.25, 0.75)
                            print(f"[Poster Native] Sliding mouse to text area at ({tx}, {ty}) and focusing...")
                            smooth_move_mouse_with_cursor(page, tx, ty)
                            time.sleep(random.uniform(1.0, 2.0)) # Nghỉ ngẫu nhiên 1-2s trước khi focus
                            page.mouse.click(tx, ty)
                            time.sleep(random.uniform(1.0, 2.0)) # Nghỉ ngẫu nhiên 1-2s sau khi focus để bắt đầu gõ
                        else:
                            text_input.click(force=True)
                            time.sleep(random.uniform(1.0, 2.0))
                            
                        print(f"[Poster Native] Typing review content: {content[:30]}...")
                        text_input.fill(content)
                        time.sleep(random.uniform(1.0, 2.0)) # Nghỉ ngẫu nhiên 1-2s sau khi gõ xong
                    else:
                        print("[Poster Native Warning] Review text area not found!")
            except Exception as input_err:
                print(f"[Poster Native Warning] Star selection or content typing failed: {input_err}")
            # ----------------------------------------

            # 3. Tự động click Đăng / Post nếu auto_submit = True
            is_submitted = False
            if auto_submit:
                try:
                    print("[Poster Native] Auto submit is enabled. Finding Post button...")
                    submit_selectors = [
                        'button:has-text("Đăng")',
                        'button:has-text("Post")',
                        'button:has-text("Publish")',
                        '[role="button"]:has-text("Đăng")',
                        '[role="button"]:has-text("Post")',
                        '[role="button"]:has-text("Publish")',
                        'span:has-text("Đăng")',
                        'span:has-text("Post")'
                    ]
                    submit_btn = None
                    for sel in submit_selectors:
                        try:
                            btn = target_root.locator(sel).first
                            if btn.is_visible():
                                submit_btn = btn
                                print(f"[Poster Native] Found visible submit button using selector: '{sel}'")
                                break
                        except Exception:
                            pass
                    
                    if submit_btn:
                        box_submit = submit_btn.bounding_box()
                        if box_submit:
                            # Điểm nhấp dao động ngẫu nhiên 25% - 75% trên diện tích nút Đăng
                            sx = box_submit["x"] + box_submit["width"] * random.uniform(0.25, 0.75)
                            sy = box_submit["y"] + box_submit["height"] * random.uniform(0.25, 0.75)
                            print(f"[Poster Native] Sliding mouse to submit button at ({sx}, {sy}) and clicking...")
                            smooth_move_mouse_with_cursor(page, sx, sy)
                            time.sleep(random.uniform(1.5, 3.0)) # Nghỉ ngẫu nhiên trước khi click
                            page.mouse.click(sx, sy)
                        else:
                            submit_btn.click(force=True)
                        print("[Poster Native] Clicked submit button. Waiting 30s for Google to process submission...")
                        time.sleep(30)
                        is_submitted = True
                    else:
                        print("[Poster Native Warning] Submit button not found in active review popup context.")
                except Exception as submit_err:
                    print(f"[Poster Native Warning] Auto submit click failed: {submit_err}")

            # Giữ trình duyệt mở cho người dùng tự do thao tác dán bài và đăng (Thoát ngay khi người dùng đóng Chrome)
            if not is_submitted and not headless:
                for _ in range(600):
                    time.sleep(1)
                    try:
                        if proc.poll() is not None or page.is_closed() or not context.pages:
                            print("[Poster Native CDP] Chrome window closed by user.")
                            break
                        page.title()
                    except Exception:
                        print("[Poster Native CDP] Detected browser close. Exiting loop.")
                        break
            else:
                print("[Poster Native CDP] Finished task. Disconnecting browser...")

            try:
                browser.disconnect()
            except Exception:
                pass

        except Exception as p_err:
            print(f"[Poster Native CDP Error] Playwright execution error: {p_err}")

        finally:
            # Đảm bảo tiến trình Chrome luôn được đóng sạch khi xong việc
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    return is_submitted



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
    headless: bool = False,
    auto_submit: bool = False
) -> dict:
    """
    Dịch vụ mở trình duyệt trực quan trên Google Search & tự động kích hoạt Popup 'Viết bài đánh giá'.
    """
    target_rating = int(rating) if rating else 5
    
    # 0. Tự động phân bổ hình ảnh nếu không được truyền từ client
    if not images:
        images = []
        try:
            from app.models.business import Business
            from app.models.history import ReviewHistory
            from app.models.draft import ReviewDraft
            from sqlalchemy.future import select
            import glob
            import random
            
            # Lấy thông tin Business
            biz_res = await db.execute(
                select(Business).where(
                    (Business.place_id == place_id) | (Business.name == business_name)
                )
            )
            biz = biz_res.scalars().first()
            
            if biz:
                used_images = set()
                # 1. Tìm các ảnh đã có trong Lịch sử Đăng bài (ReviewHistory)
                hist_res = await db.execute(
                    select(ReviewHistory).where(ReviewHistory.business_id == biz.id)
                )
                history_records = hist_res.scalars().all()
                for hr in history_records:
                    if isinstance(hr.reviews, list):
                        for r_item in hr.reviews:
                            if isinstance(r_item, dict) and r_item.get("images"):
                                for img in r_item["images"]:
                                    used_images.add(os.path.abspath(img).lower())
                                    
                # 2. Tìm các ảnh đã được phân bổ trong các bài nháp khác (ReviewDraft)
                draft_res = await db.execute(
                    select(ReviewDraft).where(ReviewDraft.business_id == biz.id)
                )
                draft_record = draft_res.scalars().first()
                if draft_record and isinstance(draft_record.reviews, list):
                    for r_item in draft_record.reviews:
                        if isinstance(r_item, dict) and r_item.get("images"):
                            r_content = r_item.get("content", "").strip()
                            if r_content != content.strip():
                                for img in r_item["images"]:
                                    used_images.add(os.path.abspath(img).lower())

                # 3. Quét tất cả các ảnh trong thư mục cấu hình CSDL
                all_available_images = []
                from app.models.settings import SystemSetting
                setting_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "image_folder_path"))
                setting_rec = setting_res.scalars().first()
                hinh_google_root = (setting_rec.value if setting_rec and setting_rec.value else r"C:\hinh_google").strip()
                if os.path.exists(hinh_google_root):
                    from app.services.poster import to_unsigned_snake_case
                    clean_snake_name = to_unsigned_snake_case(biz.name)
                    biz_dir_snake = os.path.join(hinh_google_root, clean_snake_name)
                    clean_biz_name = re.sub(r'[\\/*?:"<>|]', '', biz.name).strip()
                    biz_dir = os.path.join(hinh_google_root, clean_biz_name)
                    biz_dir_raw = os.path.join(hinh_google_root, biz.name.strip())
                    
                    target_dir = None
                    if os.path.exists(biz_dir_snake) and os.path.isdir(biz_dir_snake):
                        target_dir = biz_dir_snake
                    elif os.path.exists(biz_dir) and os.path.isdir(biz_dir):
                        target_dir = biz_dir
                    elif os.path.exists(biz_dir_raw) and os.path.isdir(biz_dir_raw):
                        target_dir = biz_dir_raw
                    
                    if target_dir:
                        print(f"[Poster Allocation] Scanning directory: {target_dir}")
                        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"):
                            all_available_images.extend(glob.glob(os.path.join(target_dir, ext)))
                            all_available_images.extend(glob.glob(os.path.join(target_dir, ext.upper())))
                    else:
                        print(f"[Poster Allocation] Scanning root C:\\hinh_google...")
                        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"):
                            all_available_images.extend(glob.glob(os.path.join(hinh_google_root, ext)))
                            all_available_images.extend(glob.glob(os.path.join(hinh_google_root, ext.upper())))
                
                # 4. Lọc bỏ trùng lặp và chuyển thành đường dẫn tuyệt đối
                all_available_images = list(set([os.path.abspath(p) for p in all_available_images]))
                unselected_images = [p for p in all_available_images if p.lower() not in used_images]
                
                print(f"[Poster Allocation] Total available: {len(all_available_images)}, Used: {len(used_images)}, Unused: {len(unselected_images)}")
                
                # 5. Phân bổ ngẫu nhiên từ 1 đến 4 ảnh từ danh sách chưa sử dụng
                if unselected_images:
                    num_to_select = min(random.randint(1, 4), len(unselected_images))
                    images = random.sample(unselected_images, num_to_select)
                    print(f"[Poster Allocation] Selected {num_to_select} images: {images}")
                else:
                    print("[Poster Allocation] No unselected images left.")
        except Exception as alloc_err:
            print(f"[Poster Allocation Error] Failed to allocate images: {alloc_err}")
    
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
            headless,
            business_name,
            auto_submit
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
                "message": f"Bài review cho {business_name} đã được đăng thành công trên Google Maps!",
                "images": images
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
            "message": f"Đã mở Google Search và Popup đánh giá cho {business_name}. Bạn hãy tự chọn số sao, dán nội dung và bấm Đăng trên Chrome.",
            "images": images
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


