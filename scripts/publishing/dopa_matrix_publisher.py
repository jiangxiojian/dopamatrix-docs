"""Simple Windows launcher for the DopaMatrix assisted publishing workbench.

The launcher keeps Python arguments away from operators. It selects a delivery
package, creates a publish plan when needed, starts the local workbench, and
opens it in the default browser. Final TikTok/Facebook publishing remains a
manual operator action.
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bitbrowser_rpa_example import DEFAULT_BIT_API, DEFAULT_DELIVERY_CSV_FILENAME, DEFAULT_ACCOUNT_LEDGER_FILENAME
from bitbrowser_rpa_example import main as publisher_main
from rpa_workbench_server import build_config, run_server


APP_TITLE = "DopaMatrix 发布操作台"


def find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


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
        self.server_started = False
        self.server_url = ""
        self.server_plan_csv: Path | None = None
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
            "投放包文件夹：选择本次交付包，例如 dopamatrix_delivery_1781700321(1)。里面要有文案表、账号台账和素材。",
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

        ttk.Label(scrollable, text="投放包文件夹").grid(row=0, column=0, sticky="w", pady=8)
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
                "3. 投放包内有矩阵投放文案对照表.csv、账号环境台账.csv 和素材\n"
                "4. 脚本只准备草稿，不会点击 TK/FB 的最终发布按钮"
            ),
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(scrollable, textvariable=self.status, foreground="#185abc", wraplength=820).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(12, 8)
        )

        footer = ttk.Frame(self, padding=(22, 8, 22, 20))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="打开已有计划", command=self.open_existing_plan).grid(row=0, column=1, padx=6)
        ttk.Button(footer, text="生成计划并打开操作台", command=self.start_workbench).grid(row=0, column=2)

    def choose_delivery_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择 DopaMatrix 投放包文件夹")
        if selected:
            self.delivery_dir.set(selected)
            self.status.set("已选择投放包，请确认文件后启动操作台。")

    def package_paths(self) -> tuple[Path, Path, Path]:
        root = Path(self.delivery_dir.get().strip()).expanduser().resolve()
        return root, root / DEFAULT_DELIVERY_CSV_FILENAME, root / DEFAULT_ACCOUNT_LEDGER_FILENAME

    def validate_package(self, require_inputs: bool = True) -> tuple[Path, Path, Path]:
        root, delivery_csv, ledger_csv = self.package_paths()
        if not root.is_dir():
            raise ValueError("投放包文件夹不存在。")
        if require_inputs and not delivery_csv.is_file():
            raise ValueError(f"缺少 {DEFAULT_DELIVERY_CSV_FILENAME}。")
        if require_inputs and not ledger_csv.is_file():
            raise ValueError(f"缺少 {DEFAULT_ACCOUNT_LEDGER_FILENAME}。")
        return root, delivery_csv, ledger_csv

    def create_plan_if_needed(self, root: Path, delivery_csv: Path, ledger_csv: Path) -> Path:
        plan_csv = root / "publish_plan.csv"
        if plan_csv.is_file():
            return plan_csv
        argv = [
            "--generate-plan",
            "--delivery-dir",
            str(root),
            "--delivery-csv",
            str(delivery_csv),
            "--account-ledger",
            str(ledger_csv),
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
            account_ledger=str(plan_csv.parent / DEFAULT_ACCOUNT_LEDGER_FILENAME),
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
            plan_csv = root / "publish_plan.csv"
            if not plan_csv.is_file():
                raise ValueError("当前文件夹没有 publish_plan.csv，请先生成发布计划。")
            self.start_workbench_for_plan(plan_csv)
        except Exception as exc:
            self.status.set(f"打开失败：{exc}")
            messagebox.showerror(APP_TITLE, str(exc))


def main() -> int:
    app = PublisherLauncher()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
