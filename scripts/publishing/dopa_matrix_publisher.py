"""Simple Windows launcher for the DopaMatrix assisted publishing workbench.

The launcher keeps Python arguments away from operators. It selects a delivery
package, creates a publish plan when needed, starts the local workbench, and
opens it in the default browser. Final TikTok/Facebook publishing remains a
manual operator action.
"""

from __future__ import annotations

import argparse
import csv
import json
import queue
import sys
import socket
import threading
import time
import traceback
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bitbrowser_rpa_example import (
    ACCOUNT_LEDGER_FIELDS,
    BitBrowserClient,
    DEFAULT_ACCOUNT_LEDGER_FILENAME,
    DEFAULT_BIT_API,
    DEFAULT_DELIVERY_CSV_FILENAME,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    default_delivery_plan_path,
    default_delivery_work_dir,
    existing_delivery_plan_path,
    extract_bitbrowser_profile_rows,
    merge_account_ledger_rows,
    normalize_account_ledger_row,
    read_account_ledger_rows,
    scan_media_files,
    write_account_ledger_rows,
)
from bitbrowser_rpa_example import main as publisher_main
from rpa_workbench_server import build_config, run_server


APP_TITLE = "DopaMatrix 发布操作台"
LEDGER_PREVIEW_COLUMNS = ("account_key", "platform", "profile_name", "profile_id", "content_check_action", "default", "health_status")
LEDGER_FIELD_SPECS = [
    ("account_key", "账号键", "entry", None, 30),
    ("platform", "平台", "combo", ("", "tiktok", "facebook"), 18),
    ("profile_id", "窗口ID", "entry", None, 34),
    ("profile_name", "窗口名称", "entry", None, 34),
    ("content_check_action", "内容检查处理", "combo", ("", "pause", "enable", "cancel"), 18),
    ("default", "默认", "combo", ("", "Y", "N"), 10),
    ("health_status", "健康状态", "combo", ("", "OK", "WATCH", "BLOCKED", "LOGIN_REQUIRED", "PROXY_ISSUE", "PAGE_ACCESS_ISSUE"), 22),
    ("last_checked_at", "最近检查时间", "entry", None, 30),
    ("owner_type", "归属类型", "combo", ("", "self", "client", "shared"), 18),
    ("owner_client_id", "客户ID", "entry", None, 24),
    ("authorization_type", "授权方式", "combo", ("", "direct_login", "business_role", "managed"), 20),
    ("daily_publish_limit", "每日上限", "entry", None, 16),
    ("region", "地区", "entry", None, 16),
    ("proxy_region", "代理地区", "entry", None, 16),
    ("proxy_provider", "代理供应商", "entry", None, 20),
    ("notes", "备注", "entry", None, 40),
    ("health_note", "健康备注", "entry", None, 40),
]


def find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def fill_missing_plan_metadata(plan_csv: Path, client_id: str = "", product_id: str = "", operator: str = "") -> int:
    updates = {
        "client_id": client_id.strip(),
        "product_id": product_id.strip(),
        "operator": operator.strip(),
    }
    updates = {key: value for key, value in updates.items() if value}
    if not updates:
        return 0

    with plan_csv.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = [{key: value or "" for key, value in row.items()} for row in reader]
    if not rows:
        return 0
    for key in updates:
        if key not in fieldnames:
            fieldnames.append(key)

    changed = 0
    for row in rows:
        row_changed = False
        for key, value in updates.items():
            if not (row.get(key) or "").strip():
                row[key] = value
                row_changed = True
        if row_changed:
            changed += 1
    if not changed:
        return 0
    with plan_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return changed


class PublisherLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x720")
        self.minsize(840, 620)
        self.delivery_dir = tk.StringVar()
        self.client_id = tk.StringVar()
        self.product_id = tk.StringVar()
        self.operator = tk.StringVar()
        self.status = tk.StringVar(value="请选择一个投放包文件夹。")
        self.package_check = tk.StringVar(value="投放包检查：尚未选择文件夹。")
        self.server_started = False
        self.server_url = ""
        self.server_plan_csv: Path | None = None
        self.ledger_editor: LedgerEditorWindow | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(3, weight=0)

        header = ttk.Frame(self, padding=(22, 20, 22, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_TITLE, font=("Microsoft YaHei UI", 18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="选择投放包后，系统会生成计划并打开浏览器操作台。最终发布仍由人工确认。",
            foreground="#667085",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        help_frame = ttk.LabelFrame(self, text="字段说明", padding=(14, 10))
        help_frame.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 10))
        help_frame.columnconfigure(0, weight=1)
        help_texts = [
            "投放包文件夹：选择 dopamatrix_delivery_xxx 这一层，例如 dopamatrix_delivery_1781700321(1)。不要选择 videos、images 或单个素材文件。",
            "标准目录：视频放 videos 文件夹，图片放 images 文件夹；文案表和账号台账放在投放包根目录。",
            "脚本产物：发布计划、日志、汇总和报告默认放到 rpa_work 文件夹，避免把投放包根目录堆乱。",
            "素材文件名：矩阵投放文案对照表.csv 里的素材文件名要能在 videos 或 images 里找到。",
            "客户 ID：可选。用来把发布任务、帖子链接、询盘和报告归到同一个客户；正式发布建议按团队客户台账填写，例如 CUST_A。",
            "产品 ID：可选。用来区分同一客户下的不同产品、活动或投放批次；正式发布建议按产品/项目编号填写，例如 TOILET_001。",
            "测试时不填也能运行；随便填也能运行，但后续报告和回查会按你填的值统计。",
            "操作人：当前执行这次发布的人名或账号名，会记录到日志里，方便回查。",
        ]
        for index, text in enumerate(help_texts):
            ttk.Label(help_frame, text=f"• {text}", wraplength=860, justify="left").grid(
                row=index, column=0, sticky="w", pady=2
            )

        form_host = ttk.Frame(self, padding=(22, 0, 22, 10))
        form_host.grid(row=2, column=0, sticky="nsew")
        form_host.columnconfigure(0, weight=1)
        form_host.rowconfigure(0, weight=1)

        canvas = tk.Canvas(form_host, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(form_host, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.columnconfigure(1, weight=1)
        scroll_window = canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def sync_scrollregion(_event: tk.Event[tk.Misc] | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_canvas_width(event: tk.Event[tk.Misc]) -> None:
            canvas.itemconfigure(scroll_window, width=event.width)

        def on_mousewheel(event: tk.Event[tk.Misc]) -> None:
            delta = getattr(event, "delta", 0)
            if delta:
                canvas.yview_scroll(int(-1 * (delta / 120)), "units")

        scrollable.bind("<Configure>", sync_scrollregion)
        canvas.bind("<Configure>", sync_canvas_width)
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        ttk.Label(scrollable, text="投放包文件夹（选 dopamatrix_delivery_xxx 这一层）").grid(
            row=0, column=0, sticky="w", pady=8
        )
        ttk.Entry(scrollable, textvariable=self.delivery_dir).grid(row=0, column=1, sticky="ew", padx=10, pady=8)
        ttk.Button(scrollable, text="选择文件夹", command=self.choose_delivery_dir).grid(row=0, column=2, pady=8)

        ttk.Label(scrollable, text="客户 ID（可选）").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(scrollable, textvariable=self.client_id).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=10, pady=8
        )

        ttk.Label(scrollable, text="产品 ID（可选）").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Entry(scrollable, textvariable=self.product_id).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=10, pady=8
        )

        ttk.Label(scrollable, text="操作人（可选）").grid(row=3, column=0, sticky="w", pady=8)
        ttk.Entry(scrollable, textvariable=self.operator).grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=10, pady=8
        )

        checklist = ttk.LabelFrame(scrollable, text="开始前确认", padding=12)
        checklist.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(18, 8))
        checklist.columnconfigure(0, weight=1)
        ttk.Label(
            checklist,
            text=(
                "1. 比特浏览器已启动，Local API 已开启\n"
                "2. TK / FB 账号已在对应环境登录，代理已确认\n"
                "3. 投放包根目录有文案表和账号台账；视频在 videos，图片在 images\n"
                "4. 脚本只准备草稿，不会点击 TK/FB 的最终发布按钮"
            ),
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(scrollable, textvariable=self.status, foreground="#185abc", wraplength=820).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(12, 8)
        )
        ttk.Label(scrollable, textvariable=self.package_check, foreground="#344054", wraplength=820, justify="left").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )

        footer = ttk.Frame(self, padding=(22, 8, 22, 20))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="同步台账", command=self.open_ledger_editor).grid(row=0, column=0, padx=6)
        ttk.Button(footer, text="打开已有计划", command=self.open_existing_plan).grid(row=0, column=1, padx=6)
        ttk.Button(footer, text="生成计划并打开操作台", command=self.start_workbench).grid(row=0, column=2)

    def choose_delivery_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择 DopaMatrix 投放包文件夹")
        if selected:
            self.delivery_dir.set(selected)
            self.refresh_package_check()

    def package_paths(self) -> tuple[Path, Path, Path]:
        root = Path(self.delivery_dir.get().strip()).expanduser().resolve()
        return root, root / DEFAULT_DELIVERY_CSV_FILENAME, root / DEFAULT_ACCOUNT_LEDGER_FILENAME

    @staticmethod
    def selected_media_subdir(root: Path) -> str:
        name = root.name.lower()
        if name in {"videos", "images"}:
            return name
        return ""

    def validate_package(self, require_inputs: bool = True) -> tuple[Path, Path, Path]:
        root, delivery_csv, ledger_csv = self.package_paths()
        if not root.is_dir():
            raise ValueError("投放包文件夹不存在。")
        selected_subdir = self.selected_media_subdir(root)
        if selected_subdir:
            raise ValueError(f"当前选到了 {selected_subdir} 素材文件夹，请选择上一层 dopamatrix_delivery_xxx 投放包。")
        if require_inputs and not delivery_csv.is_file():
            raise ValueError(f"缺少 {DEFAULT_DELIVERY_CSV_FILENAME}。")
        if require_inputs and not ledger_csv.is_file():
            raise ValueError(f"缺少 {DEFAULT_ACCOUNT_LEDGER_FILENAME}。")
        return root, delivery_csv, ledger_csv

    def refresh_package_check(self) -> None:
        try:
            root, delivery_csv, ledger_csv = self.package_paths()
            if not root.is_dir():
                self.status.set("请选择投放包文件夹。")
                self.package_check.set("投放包检查：文件夹不存在。")
                return
            selected_subdir = self.selected_media_subdir(root)
            if selected_subdir:
                parent = root.parent
                self.status.set(f"当前选到了 {selected_subdir} 素材文件夹，请选择上一层投放包。")
                self.package_check.set(
                    "投放包检查：\n"
                    f"!!  请选择上一层文件夹：{parent}\n"
                    "OK  videos 用来放视频素材\n"
                    "OK  images 用来放图片素材"
                )
                return
            videos_dir = root / "videos"
            images_dir = root / "images"
            work_dir = default_delivery_work_dir(root)
            video_count = len(scan_media_files(videos_dir, VIDEO_EXTENSIONS)) if videos_dir.is_dir() else 0
            image_count = len(scan_media_files(images_dir, IMAGE_EXTENSIONS)) if images_dir.is_dir() else 0
            total_media_count = len(scan_media_files(root, VIDEO_EXTENSIONS | IMAGE_EXTENSIONS))
            plan_csv = existing_delivery_plan_path(root)
            default_plan_csv = default_delivery_plan_path(root)
            lines = [
                "投放包检查：",
                self.check_line(delivery_csv.is_file(), f"找到 {DEFAULT_DELIVERY_CSV_FILENAME}", f"缺少 {DEFAULT_DELIVERY_CSV_FILENAME}"),
                self.check_line(ledger_csv.is_file(), f"找到 {DEFAULT_ACCOUNT_LEDGER_FILENAME}", f"缺少 {DEFAULT_ACCOUNT_LEDGER_FILENAME}"),
                self.check_line(
                    videos_dir.is_dir(),
                    f"找到 videos 文件夹，视频 {video_count} 个；视频素材放这里",
                    "没有 videos 文件夹；如果只发图片可以忽略",
                ),
                self.check_line(
                    images_dir.is_dir(),
                    f"找到 images 文件夹，图片 {image_count} 个；图片素材放这里",
                    "没有 images 文件夹；如果只发视频可以忽略",
                ),
                self.check_line(total_media_count > 0, f"共找到素材 {total_media_count} 个", "没有找到视频或图片素材"),
                self.check_line(
                    work_dir.is_dir(),
                    f"找到 rpa_work 工作目录：{work_dir}",
                    "未找到 rpa_work 工作目录；点击生成按钮会自动创建",
                ),
                self.check_line(
                    bool(plan_csv),
                    f"找到已有计划表：{plan_csv}",
                    f"未找到计划表，点击生成按钮会创建：{default_plan_csv}",
                ),
            ]
            self.package_check.set("\n".join(lines))
            if delivery_csv.is_file() and ledger_csv.is_file() and total_media_count > 0:
                self.status.set("投放包检查通过，可以生成计划或打开已有计划。")
            else:
                self.status.set("投放包还缺必要文件，请按检查结果补齐。")
        except Exception as exc:
            self.status.set(f"投放包检查失败：{exc}")
            self.package_check.set("投放包检查：失败。")

    @staticmethod
    def check_line(ok: bool, ok_text: str, bad_text: str) -> str:
        return ("OK  " if ok else "!!  ") + (ok_text if ok else bad_text)

    def create_plan_if_needed(self, root: Path, delivery_csv: Path, ledger_csv: Path) -> Path:
        plan_csv = existing_delivery_plan_path(root)
        if plan_csv:
            updated_count = self.fill_missing_plan_metadata(plan_csv)
            if updated_count:
                self.status.set(f"已更新已有计划表的客户/产品信息：{updated_count} 行。")
            return plan_csv
        plan_csv = default_delivery_plan_path(root)
        argv = [
            "--generate-plan",
            "--delivery-dir",
            str(root),
            "--delivery-csv",
            str(delivery_csv),
            "--account-ledger",
            str(ledger_csv),
            "--output-plan-csv",
            str(plan_csv),
            "--plan-client-id",
            self.client_id.get().strip(),
            "--plan-product-id",
            self.product_id.get().strip(),
            "--plan-operator",
            self.operator.get().strip(),
        ]
        result = publisher_main(argv)
        if result != 0 or not plan_csv.is_file():
            raise RuntimeError("发布计划生成失败，请检查投放包文件和账号台账。")
        return plan_csv

    def fill_missing_plan_metadata(self, plan_csv: Path) -> int:
        return fill_missing_plan_metadata(
            plan_csv,
            client_id=self.client_id.get(),
            product_id=self.product_id.get(),
            operator=self.operator.get(),
        )

    def start_workbench_for_plan(self, plan_csv: Path) -> None:
        if self.server_started:
            if self.server_plan_csv != plan_csv.resolve():
                raise ValueError("当前操作台已经打开了另一个投放包，请关闭当前启动器后再打开新的投放包。")
            webbrowser.open(self.server_url)
            return
        port = find_free_port()
        args = argparse.Namespace(
            plan_csv=str(plan_csv),
            log_jsonl="",
            summary_csv="",
            customer_report_detail_csv="",
            customer_report_overview_csv="",
            customer_report_html="",
            account_health_csv="",
            account_ledger=str(self.find_account_ledger_for_plan(plan_csv)),
            bit_api=DEFAULT_BIT_API,
            operator=self.operator.get().strip(),
            host="127.0.0.1",
            port=port,
            open_browser=False,
        )
        # Validate the same config the server will use before opening a tab.
        build_config(args)
        thread = threading.Thread(target=run_server, args=(args,), daemon=True)
        thread.start()
        self.server_started = True
        url = f"http://127.0.0.1:{port}/"
        self.server_url = url
        self.server_plan_csv = plan_csv.resolve()
        self.status.set(f"操作台已启动：{url}")
        for _ in range(20):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                    break
            except OSError:
                time.sleep(0.1)
        webbrowser.open(url)

    def start_workbench(self) -> None:
        try:
            root, delivery_csv, ledger_csv = self.validate_package(require_inputs=True)
            self.status.set("正在检查投放包并生成发布计划，请稍候……")
            self.update_idletasks()
            plan_csv = self.create_plan_if_needed(root, delivery_csv, ledger_csv)
            self.start_workbench_for_plan(plan_csv)
        except Exception as exc:
            self.status.set(f"启动失败：{exc}")
            messagebox.showerror(APP_TITLE, str(exc))

    def open_existing_plan(self) -> None:
        try:
            root, _, _ = self.validate_package(require_inputs=False)
            plan_csv = existing_delivery_plan_path(root)
            if not plan_csv:
                raise ValueError("当前投放包没有计划表，请先生成发布计划。")
            self.start_workbench_for_plan(plan_csv)
        except Exception as exc:
            self.status.set(f"打开失败：{exc}")
            messagebox.showerror(APP_TITLE, str(exc))

    def open_ledger_editor(self) -> None:
        try:
            root, _, _ = self.validate_package(require_inputs=False)
            ledger_path = root / DEFAULT_ACCOUNT_LEDGER_FILENAME
            if self.ledger_editor and self.ledger_editor.winfo_exists():
                self.ledger_editor.lift()
                self.ledger_editor.focus_force()
                self.ledger_editor.load_ledger_path(ledger_path)
                return
            self.ledger_editor = LedgerEditorWindow(self, root, ledger_path, DEFAULT_BIT_API)
        except Exception as exc:
            self.status.set(f"打开台账失败：{exc}")
            messagebox.showerror(APP_TITLE, str(exc))

    @staticmethod
    def find_account_ledger_for_plan(plan_csv: Path) -> Path:
        for parent in [plan_csv.parent, *plan_csv.parents]:
            candidate = parent / DEFAULT_ACCOUNT_LEDGER_FILENAME
            if candidate.is_file():
                return candidate
        return plan_csv.parent / DEFAULT_ACCOUNT_LEDGER_FILENAME


class LedgerEditorWindow(tk.Toplevel):
    def __init__(self, master: PublisherLauncher, package_root: Path, ledger_path: Path, bit_api: str) -> None:
        super().__init__(master)
        self.master_launcher = master
        self.package_root = package_root
        self.ledger_path = ledger_path
        self.bit_api = bit_api
        self.title(f"{APP_TITLE} - 台账同步")
        self.geometry("1120x720")
        self.minsize(940, 580)
        self.rows: list[dict[str, str]] = []
        self.current_index: int | None = None
        self.dirty = False
        self.last_sync_count = 0
        self._syncing = False
        self._tree_select_updating = False
        self._sync_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)
        self.summary_var = tk.StringVar(value="尚未同步 BitBrowser 窗口。")
        self.path_var = tk.StringVar(value=str(self.ledger_path))
        self.status_var = tk.StringVar(value="先同步窗口，再补必要字段，然后保存。")
        self.field_vars = {field: tk.StringVar() for field in ACCOUNT_LEDGER_FIELDS}
        self.field_widgets: dict[str, tk.Widget] = {}
        self.sync_buttons: list[ttk.Widget] = []
        self._build_ui()
        self.load_ledger_from_disk()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.transient(master)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(3, weight=0)

        header = ttk.Frame(self, padding=(20, 16, 20, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="BitBrowser 台账同步器", font=("Microsoft YaHei UI", 17, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="先拉取窗口，再在这里补账号键、平台和归因信息，最后保存回投放包根目录。",
            foreground="#667085",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.path_var, foreground="#475467").grid(row=2, column=0, sticky="w", pady=(6, 0))

        toolbar = ttk.Frame(self, padding=(20, 0, 20, 10))
        toolbar.grid(row=1, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)
        sync_button = ttk.Button(toolbar, text="同步 BitBrowser 窗口", command=self.sync_from_bitbrowser)
        sync_button.grid(row=0, column=0, padx=(0, 6))
        self.sync_buttons.append(sync_button)
        load_button = ttk.Button(toolbar, text="载入本地台账", command=self.load_ledger_from_disk)
        load_button.grid(row=0, column=1, padx=6)
        self.sync_buttons.append(load_button)
        add_button = ttk.Button(toolbar, text="新增空行", command=self.add_blank_row)
        add_button.grid(row=0, column=2, padx=6)
        self.sync_buttons.append(add_button)
        delete_button = ttk.Button(toolbar, text="删除当前行", command=self.delete_current_row)
        delete_button.grid(row=0, column=3, padx=6)
        self.sync_buttons.append(delete_button)
        save_button = ttk.Button(toolbar, text="保存到投放包", command=self.save_ledger)
        save_button.grid(row=0, column=4, padx=6)
        self.sync_buttons.append(save_button)
        ttk.Button(toolbar, text="关闭", command=self.close).grid(row=0, column=5, padx=6)

        summary_shell = ttk.Frame(self, padding=(20, 0, 20, 10))
        summary_shell.grid(row=2, column=0, sticky="nsew")
        summary_shell.columnconfigure(0, weight=1)
        summary_shell.rowconfigure(0, weight=1)

        self.summary_canvas = tk.Canvas(summary_shell, highlightthickness=0, borderwidth=0)
        self.summary_canvas.grid(row=0, column=0, sticky="nsew")
        summary_scroll_y = ttk.Scrollbar(summary_shell, orient="vertical", command=self.summary_canvas.yview)
        summary_scroll_y.grid(row=0, column=1, sticky="ns")
        self.summary_canvas.configure(yscrollcommand=summary_scroll_y.set)

        summary = ttk.Frame(self.summary_canvas)
        self.summary_window = self.summary_canvas.create_window((0, 0), window=summary, anchor="nw")

        def _update_scrollregion(_event: tk.Event[tk.Misc]) -> None:
            self.summary_canvas.configure(scrollregion=self.summary_canvas.bbox("all"))

        def _sync_width(event: tk.Event[tk.Misc]) -> None:
            self.summary_canvas.itemconfigure(self.summary_window, width=event.width)

        summary.bind("<Configure>", _update_scrollregion)
        self.summary_canvas.bind("<Configure>", _sync_width)
        self.summary_canvas.bind("<Enter>", lambda _event: self.summary_canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+"))
        self.summary_canvas.bind("<Leave>", lambda _event: self.summary_canvas.unbind_all("<MouseWheel>"))

        summary.columnconfigure(0, weight=1)

        table_frame = ttk.LabelFrame(summary, text="窗口列表", padding=10)
        table_frame.grid(row=0, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(table_frame, columns=LEDGER_PREVIEW_COLUMNS, show="headings", height=9, selectmode="browse")
        tree_scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        headings = {
            "account_key": "账号键",
            "platform": "平台",
            "profile_name": "窗口名称",
            "profile_id": "窗口ID",
            "content_check_action": "内容检查",
            "default": "默认",
            "health_status": "健康状态",
        }
        widths = {
            "account_key": 160,
            "platform": 90,
            "profile_name": 160,
            "profile_id": 220,
            "content_check_action": 110,
            "default": 70,
            "health_status": 120,
        }
        for field in LEDGER_PREVIEW_COLUMNS:
            self.tree.heading(field, text=headings.get(field, field))
            self.tree.column(field, width=widths.get(field, 120), minwidth=70, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        form = ttk.LabelFrame(summary, text="当前行编辑", padding=12)
        form.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for column in range(4):
            form.columnconfigure(column, weight=1)

        for index, (field, label, kind, values, _width) in enumerate(LEDGER_FIELD_SPECS):
            row = index // 2
            col = (index % 2) * 2
            ttk.Label(form, text=label).grid(row=row * 2, column=col, sticky="w", padx=(0, 8), pady=(2, 2))
            if kind == "combo":
                widget = ttk.Combobox(form, textvariable=self.field_vars[field], values=list(values or ()), state="readonly")
            else:
                widget = ttk.Entry(form, textvariable=self.field_vars[field])
            widget.grid(row=row * 2 + 1, column=col, columnspan=2, sticky="ew", padx=(0, 12), pady=(0, 8))
            self.field_widgets[field] = widget

        action_row = ttk.Frame(summary)
        action_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        action_row.columnconfigure(0, weight=1)
        apply_button = ttk.Button(action_row, text="应用到当前行", command=self.apply_current_form)
        apply_button.grid(row=0, column=0, padx=(0, 6))
        self.sync_buttons.append(apply_button)
        save_bottom_button = ttk.Button(action_row, text="保存到投放包", command=self.save_ledger)
        save_bottom_button.grid(row=0, column=1, padx=6)
        self.sync_buttons.append(save_bottom_button)
        ttk.Label(action_row, textvariable=self.summary_var, foreground="#185abc").grid(row=0, column=2, padx=12, sticky="w")

        footer = ttk.Frame(self, padding=(20, 0, 20, 16))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, foreground="#344054").grid(row=0, column=0, sticky="w")

    @staticmethod
    def _blank_row() -> dict[str, str]:
        return {field: "" for field in ACCOUNT_LEDGER_FIELDS}

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.master_launcher.status.set(text)

    def _set_sync_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in self.sync_buttons:
            if widget.winfo_exists():
                widget.configure(state=state)

    def _on_mousewheel(self, event: tk.Event[tk.Misc]) -> str:
        canvas = getattr(self, "summary_canvas", None)
        if canvas is None:
            return "break"
        delta = getattr(event, "delta", 0)
        if delta:
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")
        return "break"

    def current_rows_copy(self) -> list[dict[str, str]]:
        return [row.copy() for row in self.rows]

    def load_ledger_from_disk(self) -> None:
        if self.ledger_path.is_file():
            self.rows = read_account_ledger_rows(self.ledger_path)
            self.set_status(f"已载入现有台账：{self.ledger_path}")
        else:
            self.rows = []
            self.set_status(f"当前还没有台账文件：{self.ledger_path}")
        self.dirty = False
        self.refresh_tree(select_first=bool(self.rows))
        self.update_summary()

    def load_ledger_path(self, ledger_path: Path) -> None:
        self.ledger_path = ledger_path
        self.path_var.set(str(self.ledger_path))
        self.load_ledger_from_disk()

    def sync_from_bitbrowser(self) -> None:
        if self._syncing:
            return
        before_rows = self.current_rows_copy() or read_account_ledger_rows(self.ledger_path)
        before_filled = self.count_filled_cells(before_rows)
        self._syncing = True
        self._set_sync_controls_enabled(False)
        self.set_status("正在同步 BitBrowser 窗口，请稍候...")
        self._sync_queue = queue.Queue(maxsize=1)
        threading.Thread(
            target=self._sync_from_bitbrowser_async,
            args=(before_rows, before_filled),
            daemon=True,
        ).start()
        self.after(100, self._poll_sync_result)

    def _sync_from_bitbrowser_async(self, before_rows: list[dict[str, str]], before_filled: int) -> None:
        try:
            client = BitBrowserClient(self.bit_api)
            profiles = client.list_profiles(page_size=200)
            discovered_rows = [normalize_account_ledger_row(profile) for profile in profiles]
            merged_rows = merge_account_ledger_rows(before_rows, discovered_rows)
            after_filled = self.count_filled_cells(merged_rows)
            self._sync_queue.put_nowait(
                (
                    "success",
                    {
                        "discovered_rows": discovered_rows,
                        "merged_rows": merged_rows,
                        "before_filled": before_filled,
                        "after_filled": after_filled,
                    },
                )
            )
        except Exception as exc:
            try:
                self._sync_queue.put_nowait(("error", exc))
            except queue.Full:
                pass

    def _poll_sync_result(self) -> None:
        if not self.winfo_exists():
            return
        try:
            kind, payload = self._sync_queue.get_nowait()
        except queue.Empty:
            if self._syncing:
                self.after(100, self._poll_sync_result)
            return
        if kind == "success" and isinstance(payload, dict):
            self._finish_sync_success(
                payload.get("discovered_rows", []),
                payload.get("merged_rows", []),
                int(payload.get("before_filled", 0)),
                int(payload.get("after_filled", 0)),
            )
            return
        if kind == "error" and isinstance(payload, Exception):
            self._finish_sync_error(payload)
            return
        self._finish_sync_error(RuntimeError("同步结果格式异常"))

    def _finish_sync_success(
        self,
        discovered_rows: list[dict[str, str]],
        merged_rows: list[dict[str, str]],
        before_filled: int,
        after_filled: int,
    ) -> None:
        if not self.winfo_exists():
            return
        self.rows = merged_rows
        self.last_sync_count = len(discovered_rows)
        self.dirty = True
        self.refresh_tree(select_first=bool(self.rows))
        self.update_summary()
        self.set_status(
            f"已同步 BitBrowser 窗口 {len(discovered_rows)} 个，台账共 {len(self.rows)} 行，"
            f"自动补齐 {max(0, after_filled - before_filled)} 个字段。"
        )
        self._syncing = False
        self._set_sync_controls_enabled(True)

    def _finish_sync_error(self, exc: Exception) -> None:
        if not self.winfo_exists():
            return
        self._syncing = False
        self._set_sync_controls_enabled(True)
        self.set_status(f"同步失败：{exc}")
        messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def refresh_tree(self, select_first: bool = False) -> None:
        if not hasattr(self, "tree"):
            return
        current_selection = self.current_index if self.current_index is not None else -1
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            values = [
                row.get("account_key", ""),
                row.get("platform", ""),
                row.get("profile_name", ""),
                row.get("profile_id", ""),
                row.get("content_check_action", ""),
                row.get("default", ""),
                row.get("health_status", ""),
            ]
            self.tree.insert("", "end", iid=str(index), values=values)
        if not self.rows:
            self.current_index = None
            self.clear_form()
            return
        target = current_selection if 0 <= current_selection < len(self.rows) else (0 if select_first else None)
        if target is None:
            self.clear_form()
            return
        self.select_row(target)

    def on_tree_select(self, _event: tk.Event[tk.Misc]) -> None:
        if self._tree_select_updating:
            return
        selection = self.tree.selection()
        if not selection:
            return
        try:
            index = int(selection[0])
        except ValueError:
            return
        if index == self.current_index:
            return
        self.select_row(index)

    def select_row(self, index: int) -> None:
        if index < 0 or index >= len(self.rows):
            return
        self.current_index = index
        self.load_row_into_form(index)
        if self.tree.selection() != (str(index),):
            self._tree_select_updating = True
            try:
                self.tree.selection_set(str(index))
            finally:
                self._tree_select_updating = False
        self.tree.see(str(index))

    def clear_form(self) -> None:
        for var in self.field_vars.values():
            var.set("")

    def load_row_into_form(self, index: int) -> None:
        row = self.rows[index]
        for field in ACCOUNT_LEDGER_FIELDS:
            self.field_vars[field].set(row.get(field, ""))
        self.update_summary()

    def apply_current_form(self) -> None:
        row = {field: self.field_vars[field].get().strip() for field in ACCOUNT_LEDGER_FIELDS}
        row["platform"] = row["platform"].lower()
        if self.current_index is None:
            self.rows.append(row)
            self.current_index = len(self.rows) - 1
        else:
            self.rows[self.current_index] = row
        self.dirty = True
        self.refresh_tree(select_first=True)
        self.update_summary()
        self.set_status("已应用当前行修改。")

    def add_blank_row(self) -> None:
        self.rows.append(self._blank_row())
        self.current_index = len(self.rows) - 1
        self.dirty = True
        self.refresh_tree(select_first=True)
        self.update_summary()
        self.set_status("已新增空行。")

    def delete_current_row(self) -> None:
        if self.current_index is None or self.current_index >= len(self.rows):
            messagebox.showinfo(APP_TITLE, "请先选择要删除的行。", parent=self)
            return
        if not messagebox.askyesno(APP_TITLE, "确定删除当前行吗？", parent=self):
            return
        del self.rows[self.current_index]
        if self.current_index >= len(self.rows):
            self.current_index = len(self.rows) - 1 if self.rows else None
        self.dirty = True
        self.refresh_tree(select_first=bool(self.rows))
        self.update_summary()
        self.set_status("已删除当前行。")

    @staticmethod
    def count_filled_cells(rows: list[dict[str, str]]) -> int:
        return sum(1 for row in rows for field in ACCOUNT_LEDGER_FIELDS if str(row.get(field, "")).strip())

    def update_summary(self) -> None:
        total_rows = len(self.rows)
        filled_cells = self.count_filled_cells(self.rows)
        total_cells = total_rows * len(ACCOUNT_LEDGER_FIELDS)
        missing_cells = max(0, total_cells - filled_cells)
        self.summary_var.set(
            f"BitBrowser 窗口 {self.last_sync_count} 个；台账 {total_rows} 行；已填 {filled_cells}/{total_cells} 个字段；待补 {missing_cells} 个字段。"
        )

    def save_ledger(self) -> None:
        try:
            self.apply_current_form()
            write_account_ledger_rows(self.ledger_path, self.rows)
            self.dirty = False
            self.set_status(f"已保存台账：{self.ledger_path}")
            messagebox.showinfo(APP_TITLE, f"已保存到\n{self.ledger_path}", parent=self)
        except Exception as exc:
            self.set_status(f"保存失败：{exc}")
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def close(self) -> None:
        if self.dirty:
            result = messagebox.askyesnocancel(APP_TITLE, "台账有未保存修改，要先保存吗？", parent=self)
            if result is None:
                return
            if result:
                self.save_ledger()
                if self.dirty:
                    return
        if self.master_launcher.ledger_editor is self:
            self.master_launcher.ledger_editor = None
        self.destroy()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump-bitbrowser-ledger", action="store_true")
    parser.add_argument("--bit-api", default=DEFAULT_BIT_API)
    args, remaining = parser.parse_known_args()
    if args.dump_bitbrowser_ledger:
        try:
            client = BitBrowserClient(args.bit_api)
            rows = client.list_profiles(page_size=200)
            print(json.dumps({"rows": rows}, ensure_ascii=True))
            return 0
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                    ensure_ascii=True,
                )
            )
            return 1
    app = PublisherLauncher()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
