import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


APP_NAME = "AI企业工作电脑客户端"
VERSION = "1.0.0"
HEARTBEAT_SECONDS = 30


def app_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "AiCompany" / "WorkstationClient"


CONFIG_PATH = app_dir() / "config.json"


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return ""


def machine_payload(bind_code: str) -> dict:
    return {
        "bind_code": bind_code.strip().upper(),
        "machine_name": socket.gethostname(),
        "ip_address": local_ip(),
        "client_version": VERSION,
        "system_info": f"Windows; User={os.environ.get('USERNAME', '')}; Client={APP_NAME}",
    }


def post_json(base_url: str, path: str, payload: dict) -> dict:
    url = base_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


class WorkstationClient(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x560")
        self.minsize(700, 520)
        self.configure(bg="#0f172a")

        self.running = False
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()

        self.base_url_var = tk.StringVar()
        self.bind_code_var = tk.StringVar()
        self.status_var = tk.StringVar(value="未连接")

        self.load_config()
        self.build_ui()

    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#0f172a")
        style.configure("Panel.TFrame", background="#172033")
        style.configure("TLabel", background="#0f172a", foreground="#dbeafe")
        style.configure("Muted.TLabel", background="#0f172a", foreground="#8fb3d9")
        style.configure("Panel.TLabel", background="#172033", foreground="#dbeafe")
        style.configure("TButton", padding=(14, 8), font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Accent.TButton", background="#06b6d4", foreground="#06121f")
        style.configure("Danger.TButton", background="#334155", foreground="#ffffff")

        root = ttk.Frame(self, padding=24)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 22))

        logo = tk.Canvas(header, width=72, height=72, bg="#0f172a", highlightthickness=0)
        logo.pack(side="left", padx=(0, 16))
        logo.create_oval(6, 6, 66, 66, fill="#eaf6ff", outline="#38bdf8", width=2)
        logo.create_oval(23, 18, 49, 52, fill="#06b6d4", outline="")
        logo.create_line(20, 28, 11, 20, fill="#0d72b9", width=3)
        logo.create_line(52, 28, 63, 20, fill="#0d72b9", width=3)
        logo.create_text(36, 37, text="AI", fill="#ffffff", font=("Segoe UI", 15, "bold"))

        title_box = ttk.Frame(header)
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text=APP_NAME, font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            title_box,
            text=f"版本 {VERSION}  ·  绑定后这台电脑会成为 AI 员工的工作电脑",
            style="Muted.TLabel",
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(6, 0))

        status = ttk.Label(header, textvariable=self.status_var, font=("Microsoft YaHei UI", 11, "bold"))
        status.pack(side="right")

        panel = ttk.Frame(root, style="Panel.TFrame", padding=20)
        panel.pack(fill="x", pady=(0, 16))

        ttk.Label(panel, text="平台地址", style="Panel.TLabel", font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        base_entry = ttk.Entry(panel, textvariable=self.base_url_var, font=("Consolas", 11))
        base_entry.grid(row=1, column=0, sticky="ew", pady=(6, 14), ipady=6)
        base_entry.insert(0, self.base_url_var.get())

        ttk.Label(panel, text="本地电脑绑定码", style="Panel.TLabel", font=("Microsoft YaHei UI", 10, "bold")).grid(row=2, column=0, sticky="w")
        bind_entry = ttk.Entry(panel, textvariable=self.bind_code_var, font=("Consolas", 14, "bold"))
        bind_entry.grid(row=3, column=0, sticky="ew", pady=(6, 14), ipady=6)

        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.grid(row=4, column=0, sticky="ew")
        ttk.Button(actions, text="启动连接", style="Accent.TButton", command=self.start).pack(side="left", padx=(0, 10))
        ttk.Button(actions, text="停止", style="Danger.TButton", command=self.stop).pack(side="left", padx=(0, 10))
        ttk.Button(actions, text="安装到本机并开机自启", command=self.install_self).pack(side="left")

        panel.columnconfigure(0, weight=1)

        log_frame = ttk.Frame(root)
        log_frame.pack(fill="both", expand=True)
        ttk.Label(log_frame, text="运行日志", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        self.log_text = tk.Text(
            log_frame,
            height=12,
            bg="#0b1220",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            relief="flat",
            padx=12,
            pady=12,
            font=("Consolas", 10),
        )
        self.log_text.pack(fill="both", expand=True)
        self.log("客户端已打开。请输入平台地址和绑定码，然后点击启动连接。")

    def load_config(self):
        try:
            if CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self.base_url_var.set(data.get("base_url", ""))
                self.bind_code_var.set(data.get("bind_code", ""))
        except Exception:
            pass

    def save_config(self):
        app_dir().mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "base_url": self.base_url_var.get().strip(),
                    "bind_code": self.bind_code_var.get().strip().upper(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def log(self, message: str):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.insert("end", f"[{stamp}] {message}\n")
        self.log_text.see("end")

    def set_status(self, text: str):
        self.status_var.set(text)

    def start(self):
        if self.running:
            self.log("连接已在运行。")
            return
        base_url = self.base_url_var.get().strip()
        bind_code = self.bind_code_var.get().strip().upper()
        if not base_url or not bind_code:
            messagebox.showerror("缺少信息", "请填写平台地址和绑定码。")
            return
        self.save_config()
        self.running = True
        self.stop_event.clear()
        self.worker = threading.Thread(target=self.run_loop, daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.running = False
        self.set_status("已停止")
        self.log("已停止连接。")

    def run_loop(self):
        base_url = self.base_url_var.get().strip()
        bind_code = self.bind_code_var.get().strip().upper()
        payload = machine_payload(bind_code)
        try:
            result = post_json(base_url, "/api/workstations/client/bind", payload)
            self.after(0, self.set_status, "已连接")
            self.after(0, self.log, f"绑定成功：{result.get('name', socket.gethostname())}")
        except urllib.error.HTTPError as exc:
            self.after(0, self.set_status, "绑定失败")
            self.after(0, self.log, f"绑定失败：HTTP {exc.code} {exc.reason}")
            self.running = False
            return
        except Exception as exc:
            self.after(0, self.set_status, "绑定失败")
            self.after(0, self.log, f"绑定失败：{exc}")
            self.running = False
            return

        while not self.stop_event.is_set():
            try:
                post_json(base_url, "/api/workstations/client/heartbeat", machine_payload(bind_code))
                self.after(0, self.set_status, "在线")
                self.after(0, self.log, "心跳上报成功。")
            except Exception as exc:
                self.after(0, self.set_status, "网络异常")
                self.after(0, self.log, f"心跳失败：{exc}")
            self.stop_event.wait(HEARTBEAT_SECONDS)
        self.running = False

    def install_self(self):
        try:
            target_dir = app_dir()
            target_dir.mkdir(parents=True, exist_ok=True)
            source = Path(sys.executable if getattr(sys, "frozen", False) else __file__)
            target = target_dir / "AI企业工作电脑客户端.exe"
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)

            startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            startup.mkdir(parents=True, exist_ok=True)
            launcher = startup / "AI企业工作电脑客户端.cmd"
            launcher.write_text(f'@echo off\r\nstart "" "{target}"\r\n', encoding="utf-8")
            self.save_config()
            messagebox.showinfo("安装完成", f"客户端已安装到：\n{target}\n\n已添加开机自启。")
            self.log("安装完成，并已添加开机自启。")
        except Exception as exc:
            messagebox.showerror("安装失败", str(exc))
            self.log(f"安装失败：{exc}")


if __name__ == "__main__":
    client = WorkstationClient()
    client.mainloop()
