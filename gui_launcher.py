"""
GUI Control Panel cho Google Tool System
Tự động khởi chạy Backend & Frontend, hiển thị Log hệ thống thời gian thực.
Tự động dừng toàn bộ dịch vụ ngầm khi nhấn nút X đóng cửa sổ.
"""
import os
import sys
import time
import re
import subprocess
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, scrolledtext

ANSI_REGEX = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi(text: str) -> str:
    """Loại bỏ mã ANSI và dọn dẹp ký tự icon vỡ phông của Windows/Vite bằng UTF-8 chuẩn."""
    text = ANSI_REGEX.sub('', text)
    text = text.replace('âžœ', '->').replace('➜', '->')
    return text



# Cấu hình đường dẫn dự án tự động (Động 100%, tự nhận diện ổ C:, D:, E:...)
BE_DIR = os.path.dirname(os.path.abspath(__file__))

possible_fe_dirs = [
    os.path.abspath(os.path.join(BE_DIR, "..", "tool-google-fe")),
    r"C:\tool-google-fe",
    r"D:\tool-google\tool-google-fe"
]
FE_DIR = BE_DIR
for fe_path in possible_fe_dirs:
    if os.path.exists(fe_path):
        FE_DIR = fe_path
        break

VENV_PYTHON = os.path.join(BE_DIR, "venv", "Scripts", "python.exe")

class ToolLauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("🚀 Google Tool System - Trình quản lý hệ thống")
        self.geometry("850x550")
        self.configure(bg="#1e1e2e")

        # Đặt biểu tượng và style chủ đề Tối (Dark Theme)
        self.option_add("*Font", ("Consolas", 10))

        self.backend_proc = None
        self.frontend_proc = None
        self.is_stopping = False

        self._create_widgets()
        
        # Bắt sự kiện khi người dùng nhấn nút [X] đóng cửa sổ -> Dừng dịch vụ tự động
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Khởi chạy dịch vụ trong luồng phụ
        threading.Thread(target=self.start_services, daemon=True).start()

    def _create_widgets(self):
        # 1. Thanh trạng thái phía trên (Header)
        header_frame = tk.Frame(self, bg="#181825", pady=10, padx=15)
        header_frame.pack(fill=tk.X)

        title_label = tk.Label(
            header_frame, 
            text="GOOGLE TOOL SYSTEM MANAGER", 
            font=("Segoe UI", 12, "bold"), 
            fg="#cdd6f4", 
            bg="#181825"
        )
        title_label.pack(side=tk.LEFT)

        # Trạng thái Backend & Frontend
        self.status_be = tk.Label(header_frame, text="Backend: 🟡 Đang khởi động...", fg="#f9e2af", bg="#181825")
        self.status_be.pack(side=tk.RIGHT, padx=10)

        self.status_fe = tk.Label(header_frame, text="Frontend: 🟡 Đang khởi động...", fg="#f9e2af", bg="#181825")
        self.status_fe.pack(side=tk.RIGHT, padx=10)

        # 2. Khung Nút Bấm Điều Khiển
        toolbar = tk.Frame(self, bg="#1e1e2e", pady=8, padx=15)
        toolbar.pack(fill=tk.X)

        btn_open_web = tk.Button(
            toolbar, 
            text="🌐 Mở Trang Web (http://localhost:5173)", 
            command=self.open_web,
            bg="#89b4fa", 
            fg="#11111b", 
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            padx=12,
            pady=6,
            cursor="hand2"
        )
        btn_open_web.pack(side=tk.LEFT, padx=5)

        # 3. Khung Hiển Thị Log Hệ Thống (Console View)
        log_frame = tk.Frame(self, bg="#1e1e2e", padx=15, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True)

        lbl_log = tk.Label(log_frame, text="📋 Log Hệ Thống Thời Gian Thực:", fg="#a6adc8", bg="#1e1e2e", font=("Segoe UI", 9, "bold"))
        lbl_log.pack(anchor=tk.W, pady=(0, 4))

        self.log_area = scrolledtext.ScrolledText(
            log_frame, 
            bg="#11111b", 
            fg="#a6e3a1", 
            insertbackground="white",
            font=("Consolas", 9),
            relief=tk.FLAT
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def log(self, text: str, tag: str = "info"):
        if self.is_stopping:
            return
        clean_text = strip_ansi(text)
        self.log_area.insert(tk.END, clean_text + "\n")
        self.log_area.see(tk.END)

    def open_web(self):
        webbrowser.open("http://localhost:5173")

    def start_services(self):
        self.log("🚀 Đang khởi động Backend FastAPI & Frontend React...")

        # 1. Khởi chạy Backend
        try:
            python_bin = VENV_PYTHON if os.path.exists(VENV_PYTHON) else "python"
            be_cmd = [python_bin, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
            no_window = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            self.backend_proc = subprocess.Popen(
                be_cmd,
                cwd=BE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=no_window
            )
            self.status_be.config(text="Backend: 🟢 Đang chạy (8000)", fg="#a6e3a1")
            threading.Thread(target=self.read_output, args=(self.backend_proc, "[Backend]"), daemon=True).start()
        except Exception as e:
            self.log(f"❌ Lỗi khởi chạy Backend: {e}")
            self.status_be.config(text="Backend: 🔴 Lỗi!", fg="#f38ba8")

        # 2. Khởi chạy Frontend
        try:
            fe_cmd = "npm run dev"
            no_window = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            self.frontend_proc = subprocess.Popen(
                fe_cmd,
                cwd=FE_DIR,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=no_window
            )
            self.status_fe.config(text="Frontend: 🟢 Đang chạy (5173)", fg="#a6e3a1")
            threading.Thread(target=self.read_output, args=(self.frontend_proc, "[Frontend]"), daemon=True).start()
        except Exception as e:
            self.log(f"❌ Lỗi khởi chạy Frontend: {e}")
            self.status_fe.config(text="Frontend: 🔴 Lỗi!", fg="#f38ba8")

    def read_output(self, proc, prefix):
        if not proc or not proc.stdout:
            return
        for line in iter(proc.stdout.readline, ''):
            if self.is_stopping:
                break
            if line:
                self.log(f"{prefix} {line.strip()}")
        proc.stdout.close()

    def on_close(self):
        """Khi bấm X -> Tự động dừng toàn bộ dịch vụ ngầm NGAY LẬP TỨC và đóng cửa sổ trong 0.001s"""
        if self.is_stopping:
            return
        self.is_stopping = True

        no_window = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)

        # Thao tác dọn dẹp tiến trình chạy ngầm không gây giật lag GUI
        def fast_cleanup():
            # 1. Diệt toàn bộ cây tiến trình (Process Tree) của Frontend & Backend theo PID
            try:
                if self.frontend_proc and self.frontend_proc.pid:
                    subprocess.Popen(["taskkill", "/F", "/T", "/PID", str(self.frontend_proc.pid)], creationflags=no_window)
                if self.backend_proc and self.backend_proc.pid:
                    subprocess.Popen(["taskkill", "/F", "/T", "/PID", str(self.backend_proc.pid)], creationflags=no_window)
            except Exception:
                pass

            # 2. Quét diệt triệt để toàn bộ node.exe và python.exe còn sót bằng cú pháp /IM và /T chuẩn Windows
            try:
                subprocess.Popen(["taskkill", "/F", "/T", "/IM", "node.exe"], creationflags=no_window)
                subprocess.Popen(["taskkill", "/F", "/T", "/IM", "python.exe"], creationflags=no_window)
                subprocess.Popen(["taskkill", "/F", "/T", "/IM", "pythonw.exe"], creationflags=no_window)
            except Exception:
                pass

        threading.Thread(target=fast_cleanup, daemon=True).start()

        # Đóng cửa sổ giao diện tức thì
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = ToolLauncherApp()
    app.mainloop()
