"""
Local RPA confirmation workbench for DopaMatrix publishing plans.

This serves a small localhost page that reads publish_plan.csv and JSONL logs,
then writes manual confirmation results back to the CSV/JSONL files. It does
not connect to TikTok/Facebook and never clicks a platform publish button.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import mimetypes
import sys
import threading
import webbrowser
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bitbrowser_rpa_example import (  # noqa: E402
    BitBrowserClient,
    DEFAULT_ACCOUNT_LEDGER_FILENAME,
    DEFAULT_BIT_API,
    _discover_file_upwards,
    append_jsonl_log,
    connect_browser_context,
    describe_error_action,
    detect_post_url_in_context,
    extract_platform_post_id,
    load_account_ledger,
    normalize_platform_name,
    recommend_error_action,
    refresh_plan_delivery_copy,
    select_account_entry,
    update_publish_plan_row,
    write_summary_csv,
)
from bitbrowser_rpa_example import main as publisher_main  # noqa: E402
from rpa_plan_sync import sync_delivery_plan  # noqa: E402
from rpa_report_export import (  # noqa: E402
    DEFAULT_DETAIL as DEFAULT_CUSTOMER_REPORT_DETAIL,
    DEFAULT_OVERVIEW as DEFAULT_CUSTOMER_REPORT_OVERVIEW,
    export_customer_report as write_customer_report_seed,
)
from rpa_customer_report_page import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_CUSTOMER_REPORT_HTML,
    generate_report_page,
)
from rpa_operator_console import (  # noqa: E402
    latest_jsonl_rows,
    merge_rows,
    normalize_plan_row,
    normalize_summary_row,
    read_csv_rows,
    read_jsonl,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_JSONL = "publish_logs.jsonl"
DEFAULT_SUMMARY = "publish_summary.csv"
DEFAULT_ACCOUNT_HEALTH = "rpa_account_health.csv"
BACKFILL_STATUSES = {
    "PUBLISHED_MANUAL",
    "REJECTED_MANUAL",
    "PREPARED",
    "FAILED",
    "READY",
}
ACCOUNT_HEALTH_FIELDS = [
    "logged_at",
    "publish_id",
    "account_key",
    "platform",
    "profile_name",
    "health_status",
    "issue_type",
    "operator",
    "note",
]


class WorkbenchError(RuntimeError):
    pass


def idle_only(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lock:
            if self._preparation.get("running"):
                raise WorkbenchError("草稿正在准备中，请等待本批完成后再操作。")
            return method(self, *args, **kwargs)
    return guarded


@dataclass
class WorkbenchConfig:
    plan_csv: Path
    log_jsonl: Path
    summary_csv: Path
    customer_report_detail_csv: Path
    customer_report_overview_csv: Path
    customer_report_html: Path
    account_health_csv: Path
    account_ledger_csv: Path
    bit_api: str
    operator: str
    open_browser: bool = False


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_account_health(path: Path) -> list[dict[str, str]]:
    return read_csv_rows(path)


def append_account_health(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.is_file() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ACCOUNT_HEALTH_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in ACCOUNT_HEALTH_FIELDS})


def latest_health_by_account(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        account_key = row.get("account_key", "")
        if not account_key:
            continue
        current = latest.get(account_key)
        if current is None or row.get("logged_at", "") >= current.get("logged_at", ""):
            latest[account_key] = row
    return latest


class WorkbenchState:
    def __init__(self, config: WorkbenchConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._preparation: dict[str, Any] = {"running": False}
        self._delivery_sync: dict[str, Any] = {}
        self.allowed_roots = [
            Path.cwd().resolve(),
            config.plan_csv.parent.resolve(),
            config.log_jsonl.parent.resolve(),
            config.summary_csv.parent.resolve(),
            config.customer_report_detail_csv.parent.resolve(),
            config.customer_report_overview_csv.parent.resolve(),
            config.customer_report_html.parent.resolve(),
            config.account_health_csv.parent.resolve(),
            config.account_ledger_csv.parent.resolve(),
        ]

    def all_rows(self) -> list[dict[str, str]]:
        plan_rows = [normalize_plan_row(row, self.config.plan_csv) for row in read_csv_rows(self.config.plan_csv)]
        summary_rows = [normalize_summary_row(row) for row in read_csv_rows(self.config.summary_csv)]
        if not summary_rows:
            summary_rows = latest_jsonl_rows(read_jsonl(self.config.log_jsonl))
        rows = merge_rows(plan_rows, summary_rows)
        plan_index = {row["publish_id"]: row for row in plan_rows}
        accounts = self.accounts()
        health_index = latest_health_by_account(read_account_health(self.config.account_health_csv))
        for row in rows:
            plan = plan_index.get(row["publish_id"], {})
            for key in ("account_key", "profile_id", "profile_name", "status"):
                if plan.get(key):
                    row[key] = plan[key]
            if plan:
                for key in ("title", "caption", "hashtags", "tracking_url"):
                    row[key] = plan.get(key, "")
            matches = [a for a in accounts if a["account_key"] == row.get("account_key")
                       and a["platform"] == normalize_platform_name(row.get("platform", ""))]
            if len(matches) == 1:
                account = matches[0]
                row["profile_name"] = account["profile_name"]
                row["assignment_error"] = account["error"]
                if row.get("profile_id") and row["profile_id"] != account["profile_id"]:
                    row["assignment_error"] = "计划窗口与台账不一致，请重新选择账号并保存。"
                row["profile_id"] = row.get("profile_id") or account["profile_id"]
            else:
                row["assignment_error"] = "请从台账选择唯一的平台账号并保存分配。"
            row["screenshot_url"] = self.artifact_url(row.get("screenshot", ""))
            row["media_url"] = self.artifact_url(row.get("media_path", ""))
            health = health_index.get(row.get("account_key", ""))
            if health:
                row["account_health_status"] = health.get("health_status", "")
                row["account_health_issue"] = health.get("issue_type", "")
                row["account_health_note"] = health.get("note", "")
                row["account_health_at"] = health.get("logged_at", "")
        return rows

    def snapshot(self) -> dict[str, Any]:
        rows = self.all_rows()
        counts = Counter((row.get("status") or "UNKNOWN").upper() for row in rows)
        platforms = Counter((row.get("platform") or "unknown").lower() for row in rows)
        return {
            "generated_at": now_text(),
            "sources": {
                "plan_csv": str(self.config.plan_csv),
                "log_jsonl": str(self.config.log_jsonl),
                "summary_csv": str(self.config.summary_csv),
                "customer_report_detail_csv": str(self.config.customer_report_detail_csv),
                "customer_report_overview_csv": str(self.config.customer_report_overview_csv),
                "customer_report_html": str(self.config.customer_report_html),
                "account_health_csv": str(self.config.account_health_csv),
                "account_ledger_csv": str(self.config.account_ledger_csv),
                "bit_api": self.config.bit_api,
            },
            "counts": dict(counts),
            "platforms": dict(platforms),
            "tasks": rows,
            "account_health": read_account_health(self.config.account_health_csv)[-100:],
            "accounts": self.accounts(),
            "preparation": self.preparation_status(),
            "delivery_sync": self._delivery_sync,
        }

    @idle_only
    def refresh_delivery(self) -> dict[str, Any]:
        self._delivery_sync = sync_delivery_plan(self.config.plan_csv, self.config.account_ledger_csv)
        return self._delivery_sync

    def accounts(self) -> list[dict[str, str]]:
        if not read_csv_rows(self.config.account_ledger_csv):
            return []
        entries = load_account_ledger(self.config.account_ledger_csv)
        counts = Counter((normalize_platform_name(e.platform), e.account_key) for e in entries)
        accounts = []
        for entry in entries:
            platform = normalize_platform_name(entry.platform)
            error = ""
            if not entry.account_key or platform not in {"tiktok", "facebook"} or not entry.profile_id:
                error = "台账缺少账号键、平台或窗口 ID，请先补齐并保存台账。"
            elif counts[(platform, entry.account_key)] != 1:
                error = "同平台账号键重复，请先修正台账。"
            accounts.append({"account_key": entry.account_key, "platform": platform,
                             "profile_id": entry.profile_id, "profile_name": entry.profile_name,
                             "error": error})
        return accounts

    @idle_only
    def assign_account(self, body: dict[str, Any]) -> dict[str, Any]:
        task = self.find_task(clean_text(body.get("publish_id")))
        if task.get("status", "READY").upper() not in {"READY", "FAILED", "PARTIAL"}:
            raise WorkbenchError("只能修改待准备或失败任务的账号；已有草稿需先处理，再加入重试队列。")
        matches = [a for a in self.accounts() if a["account_key"] == clean_text(body.get("account_key"))
                   and a["platform"] == normalize_platform_name(task.get("platform", ""))]
        if len(matches) != 1 or matches[0]["error"]:
            raise WorkbenchError("请在本平台选择台账中资料完整且唯一的账号。")
        account = matches[0]
        updated = update_publish_plan_row(self.config.plan_csv, task["publish_id"], {
            "account_key": account["account_key"], "profile_id": account["profile_id"],
            "profile_name": account["profile_name"],
        })
        return {"updated": updated, "task": self.find_task(task["publish_id"])}

    def find_task(self, publish_id: str) -> dict[str, str]:
        for row in self.all_rows():
            if row.get("publish_id") == publish_id:
                return row
        raise WorkbenchError(f"publish_id not found: {publish_id}")

    def resolve_profile_id(self, task: dict[str, str], body: dict[str, Any] | None = None) -> str:
        body = body or {}
        profile_id = clean_text(body.get("profile_id")) or task.get("profile_id", "") or task.get("browser_profile_id", "")
        if profile_id:
            return profile_id
        account_key = clean_text(body.get("account_key")) or task.get("account_key", "")
        platform = normalize_platform_name(clean_text(body.get("platform")) or task.get("platform", ""))
        if not account_key:
            return ""
        if not self.config.account_ledger_csv.is_file():
            return ""
        entries = load_account_ledger(self.config.account_ledger_csv)
        entry = select_account_entry(entries, platform, account_key=account_key)
        return entry.profile_id if entry else ""

    @idle_only
    def backfill(self, body: dict[str, Any]) -> dict[str, Any]:
        publish_id = clean_text(body.get("publish_id"))
        status = clean_text(body.get("status")).upper()
        if not publish_id:
            raise WorkbenchError("publish_id is required.")
        if status not in BACKFILL_STATUSES:
            raise WorkbenchError(f"Unsupported status: {status}")

        task = self.find_task(publish_id)
        checked_at = now_text()
        post_url = clean_text(body.get("post_url"))
        platform_post_id = clean_text(body.get("platform_post_id"))
        published_at = clean_text(body.get("published_at"))
        manual_operator = clean_text(body.get("manual_operator")) or self.config.operator
        manual_note = clean_text(body.get("manual_note"))
        error_type = clean_text(body.get("error_type"))
        error_message = clean_text(body.get("error_message"))

        if status == "PUBLISHED_MANUAL" and not post_url:
            raise WorkbenchError("PUBLISHED_MANUAL requires post_url.")
        if status == "PUBLISHED_MANUAL" and not published_at:
            published_at = checked_at
        if status == "PUBLISHED_MANUAL" and not platform_post_id and post_url:
            platform_post_id = extract_platform_post_id(post_url, task.get("platform", ""))
        if status == "FAILED" and not error_type:
            error_type = "MANUAL_FAILED"
        if status in {"PUBLISHED_MANUAL", "REJECTED_MANUAL", "PREPARED", "READY"}:
            error_type = error_type if status == "READY" else ""
            error_message = error_message if status == "READY" else ""
        error_action = clean_text(body.get("error_action")) or recommend_error_action(error_type, status)
        error_action_label = clean_text(body.get("error_action_label")) or describe_error_action(error_action)

        updates = {
            "status": status,
            "last_result_status": status,
            "last_result_at": checked_at,
            "post_url": post_url if status == "PUBLISHED_MANUAL" else "",
            "platform_post_id": platform_post_id if status == "PUBLISHED_MANUAL" else "",
            "published_at": published_at if status == "PUBLISHED_MANUAL" else "",
            "manual_operator": manual_operator,
            "manual_checked_at": checked_at,
            "manual_note": manual_note,
            "error_type": error_type,
            "error_action": error_action,
            "error_action_label": error_action_label,
            "error_message": error_message,
        }
        updated = update_publish_plan_row(self.config.plan_csv, publish_id, updates)

        payload = {
            "plan": {
                "publish_id": publish_id,
                "plan_csv": str(self.config.plan_csv),
                "platform": task.get("platform", ""),
                "client_id": task.get("client_id", ""),
                "product_id": task.get("product_id", ""),
                "account_key": task.get("account_key", ""),
                "media_path": task.get("media_path", ""),
                "attribution_token": task.get("attribution_token", ""),
            },
            "result": {
                "status": status,
                "post_url": updates["post_url"],
                "platform_post_id": updates["platform_post_id"],
                "published_at": updates["published_at"],
                "manual_operator": manual_operator,
                "manual_checked_at": checked_at,
                "manual_note": manual_note,
                "error_type": error_type,
                "error_action": error_action,
                "error_action_label": error_action_label,
                "error_message": error_message,
                "finished_at": checked_at,
                "workbench": True,
            },
        }
        append_jsonl_log(self.config.log_jsonl, payload)
        return {"updated": updated, "task": self.find_task(publish_id)}

    @idle_only
    def detect_post_url(self, body: dict[str, Any]) -> dict[str, Any]:
        publish_id = clean_text(body.get("publish_id"))
        if not publish_id:
            raise WorkbenchError("publish_id is required.")
        task = self.find_task(publish_id)
        platform = normalize_platform_name(clean_text(body.get("platform")) or task.get("platform", ""))
        profile_id = self.resolve_profile_id(task, body)
        if not profile_id:
            raise WorkbenchError("profile_id is required.")

        bit = BitBrowserClient(self.config.bit_api)
        health = bit.health()
        opened = bit.open_profile(profile_id)
        pw = None
        browser = None
        try:
            pw, browser, context = connect_browser_context(opened.cdp_url)
            result = detect_post_url_in_context(context, platform)
            result["status"] = task.get("status", "") or "PREPARED"
            if result.get("detected"):
                result["detection_status"] = "POST_URL_DETECTED"
                result["error_action"] = recommend_error_action("", "PUBLISHED_MANUAL")
            else:
                result["error_type"] = str(result.get("error_type") or "POST_URL_NOT_FOUND")
                result["detection_status"] = result["error_type"]
                result["error_action"] = recommend_error_action(result["error_type"], result["status"])
                result["error_message"] = str(
                    result.get("error_message")
                    or "No public post URL was found in the current BitBrowser tabs."
                )
            result["error_action_label"] = describe_error_action(result.get("error_action", ""))
            payload = {
                "plan": {
                    "publish_id": publish_id,
                    "plan_csv": str(self.config.plan_csv),
                    "platform": task.get("platform", ""),
                    "client_id": task.get("client_id", ""),
                    "product_id": task.get("product_id", ""),
                    "account_key": task.get("account_key", ""),
                    "profile_id": profile_id,
                    "media_path": task.get("media_path", ""),
                    "attribution_token": task.get("attribution_token", ""),
                },
                "bitbrowser": {
                    "health": health,
                    "opened_profile": {
                        "profile_id": opened.profile_id,
                        "cdp_source": opened.cdp_source,
                    },
                    "tab_trace": {"before_detection": result.get("scanned_tabs", [])},
                },
                "result": result,
            }
            append_jsonl_log(self.config.log_jsonl, payload)
            return {
                "task": task,
                "profile_id": profile_id,
                "opened_profile": {
                    "profile_id": opened.profile_id,
                    "cdp_source": opened.cdp_source,
                },
                "result": result,
            }
        finally:
            if pw is not None:
                pw.stop()

    @idle_only
    def account_health(self, body: dict[str, Any]) -> dict[str, Any]:
        publish_id = clean_text(body.get("publish_id"))
        task = self.find_task(publish_id) if publish_id else {}
        row = {
            "logged_at": now_text(),
            "publish_id": publish_id,
            "account_key": clean_text(body.get("account_key")) or task.get("account_key", ""),
            "platform": clean_text(body.get("platform")) or task.get("platform", ""),
            "profile_name": clean_text(body.get("profile_name")) or task.get("profile_name", ""),
            "health_status": clean_text(body.get("health_status")) or "OK",
            "issue_type": clean_text(body.get("issue_type")),
            "operator": clean_text(body.get("operator")) or self.config.operator,
            "note": clean_text(body.get("note")),
        }
        if not row["account_key"]:
            raise WorkbenchError("account_key is required.")
        append_account_health(self.config.account_health_csv, row)
        return {"account_health": row}

    @idle_only
    def export_summary(self, include_history: bool = False) -> dict[str, Any]:
        rows = write_summary_csv(self.config.log_jsonl, self.config.summary_csv, include_history=include_history)
        return {"summary_csv": str(self.config.summary_csv), "rows": len(rows)}

    @idle_only
    def export_customer_report(self) -> dict[str, Any]:
        summary_rows = write_summary_csv(self.config.log_jsonl, self.config.summary_csv, include_history=False)
        result = write_customer_report_seed(
            self.config.summary_csv,
            self.config.customer_report_detail_csv,
            self.config.customer_report_overview_csv,
        )
        result["summary_rows"] = len(summary_rows)
        return result

    @idle_only
    def export_customer_report_page(self) -> dict[str, Any]:
        seed_result = self.export_customer_report()
        args = argparse.Namespace(
            detail_csv=str(self.config.customer_report_detail_csv),
            overview_csv=str(self.config.customer_report_overview_csv),
            output_html=str(self.config.customer_report_html),
            client_id="",
        )
        output = generate_report_page(args)
        return {
            **seed_result,
            "customer_report_html": str(output),
            "customer_report_url": self.artifact_url(str(output)),
        }

    @idle_only
    def prepare_tasks(self, body: dict[str, Any]) -> dict[str, Any]:
        """Prepare selected READY tasks without clicking the final publish button."""
        selected = body.get("publish_ids") or []
        if isinstance(selected, str):
            selected = [item.strip() for item in selected.split(",") if item.strip()]
        if not isinstance(selected, list):
            raise WorkbenchError("publish_ids must be a list.")
        selected = [clean_text(item) for item in selected if clean_text(item)]
        if not selected:
            raise WorkbenchError("Select at least one task to prepare.")

        requested = {item for item in selected}
        plan_rows = [normalize_plan_row(row, self.config.plan_csv) for row in read_csv_rows(self.config.plan_csv)]
        id_counts = Counter(row["publish_id"] for row in plan_rows)
        duplicate_ids = sorted(item for item in requested if id_counts[item] > 1)
        if duplicate_ids:
            raise WorkbenchError("计划表任务 ID 重复，无法确定对应素材，请先修正：" + ", ".join(duplicate_ids))
        available = {
            row.get("publish_id", "")
            for row in plan_rows
            if row.get("publish_id", "") in requested
            and (row.get("status", "READY") or "READY").upper() in {"READY", "FAILED", "PARTIAL"}
        }
        missing = sorted(requested - available)
        if missing:
            raise WorkbenchError("Tasks are not READY/FAILED/PARTIAL: " + ", ".join(missing))

        for task in self.all_rows():
            if task["publish_id"] in available and task.get("assignment_error"):
                raise WorkbenchError(f"{task['publish_id']}：{task['assignment_error']}")

        refresh_plan_delivery_copy(self.config.plan_csv, sorted(available))

        self._preparation = {
            "running": True, "publish_ids": sorted(available), "total": len(available),
            "index": 0, "publish_id": "", "message": "正在启动草稿准备，请稍候……",
            "started_at": now_text(),
        }
        thread = threading.Thread(target=self._prepare_worker, args=(sorted(available),), daemon=True)
        self._prepare_thread = thread
        try:
            thread.start()
        except Exception:
            self._preparation["running"] = False
            raise
        return self.preparation_status()

    def preparation_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._preparation)

    def _prepare_progress(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._preparation.update(event)

    def _prepare_worker(self, selected: list[str]) -> None:
        try:
            result = self._run_preparation(selected)
        except (Exception, SystemExit) as exc:
            result = {"error": str(exc), "message": f"草稿准备中断：{exc}"}
        with self._lock:
            self._preparation.update(result)
            self._preparation.update(running=False, finished_at=now_text())

    def _run_preparation(self, selected: list[str]) -> dict[str, Any]:

        argv = [
            "--plan-csv",
            str(self.config.plan_csv),
            "--only-publish-id",
            ",".join(selected),
            "--include-status",
            "READY,FAILED,PARTIAL",
            "--continue-on-error",
            "--write-plan-status",
            "--tab-mode",
            "new",
            "--facebook-upload-mode",
            "auto",
            "--log-jsonl",
            str(self.config.log_jsonl),
            "--bit-api",
            self.config.bit_api,
            "--account-ledger",
            str(self.config.account_ledger_csv),
        ]
        if self.config.operator:
            argv.extend(["--plan-operator", self.config.operator])
        exit_code = publisher_main(argv, progress_callback=self._prepare_progress)
        rows = [row for row in read_csv_rows(self.config.plan_csv)
                if normalize_plan_row(row, self.config.plan_csv)["publish_id"] in selected]
        prepared = sum(normalize_plan_row(row, self.config.plan_csv)["status"] == "PREPARED" for row in rows)
        remaining = len(selected) - prepared
        return {
            "prepared": prepared,
            "needs_attention": remaining,
            "publish_ids": selected,
            "exit_code": exit_code,
            "message": (f"本批已结束：草稿就绪 {prepared} 条，待处理 {remaining} 条。"
                        "请检查任务结果；就绪草稿仍需人工确认发布。"),
        }

    def resolve_artifact(self, path_text: str) -> Path:
        if not path_text:
            raise WorkbenchError("path is required.")
        path = Path(path_text)
        if not path.is_absolute():
            path = (self.config.plan_csv.parent / path).resolve()
        else:
            path = path.resolve()
        if not path.is_file():
            raise WorkbenchError(f"file not found: {path}")
        if not self.is_allowed_path(path):
            raise WorkbenchError(f"file is outside allowed roots: {path}")
        return path

    def artifact_url(self, path_text: str) -> str:
        if not path_text:
            return ""
        try:
            path = self.resolve_artifact(path_text)
        except Exception:
            return ""
        return f"/artifact?path={quote(str(path))}"

    def is_allowed_path(self, path: Path) -> bool:
        for root in self.allowed_roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False


def json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, text: str, content_type: str = "text/html; charset=utf-8") -> None:
    body = text.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkbenchError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(body, dict):
        raise WorkbenchError("JSON body must be an object.")
    return body


def safe_print(text: str = "") -> None:
    if sys.stdout:
        print(text)


def render_page(title: str = "RPA 确认工作台") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172026;
      --muted: #667085;
      --line: #d9e0e7;
      --panel: #f8fafc;
      --ok: #1f8a5f;
      --bad: #b42318;
      --wait: #946200;
      --blue: #185abc;
      --soft-blue: #edf4ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: var(--ink); background: #f5f7fa; }}
    header {{ padding: 18px 22px 12px; border-bottom: 1px solid var(--line); background: #fff; }}
    h1 {{ margin: 0; font-size: 22px; }}
    .topbar {{ display: flex; gap: 14px; justify-content: space-between; align-items: flex-start; }}
    .subtitle {{ margin: 6px 0 0; color: var(--muted); font-size: 13px; }}
    .stats, .toolbar, .meta, .actions, .quick-actions {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .stats {{ justify-content: flex-end; }}
    .stat {{ min-width: 86px; padding: 7px 10px; border: 1px solid var(--line); background: var(--panel); }}
    .stat strong {{ display: block; font-size: 18px; line-height: 1.1; }}
    .stat span {{ color: var(--muted); font-size: 12px; }}
    .source-details {{ margin-top: 10px; color: var(--muted); font-size: 12px; }}
    .source-details summary {{ cursor: pointer; color: var(--blue); }}
    .source {{ display: grid; gap: 4px; margin-top: 8px; overflow-wrap: anywhere; }}
    .guide {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 12px 22px; background: #fff; border-bottom: 1px solid var(--line); }}
    .guide-step {{ border: 1px solid var(--line); background: #fff; padding: 10px 12px; min-height: 64px; }}
    .guide-step strong {{ display: block; margin-bottom: 4px; }}
    .guide-step span {{ color: var(--muted); font-size: 13px; }}
    .toolbar {{ padding: 12px 22px; border-bottom: 1px solid var(--line); background: #fff; display: grid; gap: 10px; }}
    .toolbar-row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .selection {{ display: inline-flex; gap: 6px; align-items: center; color: var(--muted); font-size: 13px; }}
    input, select, textarea, button {{ font: inherit; }}
    input, select, textarea {{ border: 1px solid var(--line); padding: 8px; background: #fff; color: var(--ink); }}
    input[type="search"] {{ width: min(620px, 100%); }}
    button {{ border: 1px solid var(--line); background: #fff; color: var(--ink); padding: 8px 10px; cursor: pointer; }}
    button.primary {{ border-color: var(--blue); background: var(--blue); color: #fff; }}
    button:disabled {{ cursor: default; opacity: .55; }}
    button.soft {{ border-color: #b7cffd; background: var(--soft-blue); color: #174ea6; }}
    button.danger {{ border-color: #fecdca; color: var(--bad); background: #fff1f3; }}
    main {{ padding: 14px 22px 36px; display: grid; gap: 12px; }}
    #tasks {{ display: grid; gap: 12px; }}
    .list-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; color: var(--muted); font-size: 13px; }}
    .task {{ display: grid; grid-template-columns: 150px 1fr; border: 1px solid var(--line); background: #fff; min-height: 150px; }}
    .shot {{ border-right: 1px solid var(--line); background: #f2f5f7; display: flex; align-items: center; justify-content: center; overflow: hidden; min-height: 150px; }}
    .shot img {{ width: 100%; height: 100%; max-height: 180px; object-fit: contain; display: block; }}
    .empty-shot {{ color: var(--muted); font-size: 13px; }}
    .task-main {{ padding: 12px 14px; min-width: 0; }}
    .task-head {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; color: var(--muted); font-size: 13px; }}
    .task-select {{ width: 18px; height: 18px; accent-color: var(--blue); }}
    .badge {{ border: 1px solid var(--line); padding: 3px 7px; font-weight: 700; }}
    .badge.ok {{ color: var(--ok); border-color: #9dd8bd; background: #ecfdf3; }}
    .badge.bad {{ color: var(--bad); border-color: #fecdca; background: #fff1f3; }}
    .badge.wait {{ color: var(--wait); border-color: #fedf89; background: #fffaeb; }}
    .badge.muted {{ color: #475467; border-color: #d0d5dd; background: #f2f4f7; }}
    h2 {{ margin: 6px 0 4px; font-size: 17px; overflow-wrap: anywhere; }}
    .title {{ margin: 0 0 8px; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 8px; }}
    .next-step {{ margin: 8px 0; padding: 8px 10px; background: #fffaeb; border: 1px solid #fedf89; color: #7a4b00; font-size: 13px; }}
    .assignment {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 10px 0; font-size: 13px; }}
    .assignment select {{ max-width: 100%; min-width: 0; }}
    .assignment-window {{ overflow-wrap: anywhere; color: var(--muted); }}
    .assignment-error {{ color: var(--bad); font-size: 13px; margin: 6px 0; }}
    .preparation {{ border-top: 1px solid var(--line); padding: 10px 22px; background: #edf4ff; font-size: 13px; overflow-wrap: anywhere; }}
    .preparation[hidden] {{ display: none; }}
    .preparation progress {{ width: 180px; max-width: 100%; vertical-align: middle; margin-right: 8px; }}
    details.task-details {{ margin-top: 8px; border-top: 1px solid var(--line); padding-top: 8px; }}
    details.task-details > summary {{ cursor: pointer; color: var(--blue); font-size: 13px; }}
    .paths, .error {{ color: var(--muted); font-size: 12px; display: grid; gap: 3px; overflow-wrap: anywhere; margin-top: 8px; }}
    .error {{ color: var(--bad); margin-top: 6px; }}
    .forms {{ display: grid; grid-template-columns: minmax(260px, 1fr) minmax(260px, 1fr); gap: 12px; margin-top: 12px; border-top: 1px solid var(--line); padding-top: 12px; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(120px, 1fr)); gap: 8px; }}
    .form-grid label {{ display: grid; gap: 4px; font-size: 12px; color: var(--muted); }}
    .form-grid label.wide {{ grid-column: 1 / -1; }}
    textarea {{ min-height: 70px; resize: vertical; }}
    .toast {{ position: fixed; right: 18px; bottom: 18px; max-width: min(420px, calc(100vw - 36px)); padding: 12px 14px; border: 1px solid var(--line); background: #fff; box-shadow: 0 12px 32px rgba(16, 24, 40, .18); display: none; }}
    .toast.show {{ display: block; }}
    @media (max-width: 900px) {{
      header, .toolbar, main, .guide {{ padding-left: 12px; padding-right: 12px; }}
      .topbar {{ display: grid; }}
      .guide {{ grid-template-columns: 1fr; }}
      .task {{ grid-template-columns: 1fr; }}
      .shot {{ height: 180px; border-right: 0; border-bottom: 1px solid var(--line); }}
      .forms {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div>
        <h1>RPA 确认工作台</h1>
        <p class="subtitle">按任务准备草稿，人工检查后再发布；这里不会自动点击 TK / FB 的最终发布按钮。</p>
      </div>
      <div class="stats" id="stats"></div>
    </div>
    <details class="source-details">
      <summary>文件位置</summary>
      <div class="source" id="sources"></div>
    </details>
  </header>
  <section class="guide">
    <div class="guide-step"><strong>1. 选择任务</strong><span>勾选 READY、FAILED 或 PARTIAL 任务。</span></div>
    <div class="guide-step"><strong>2. 准备草稿</strong><span>点击“准备选中草稿”，脚本会打开页面并填素材文案。</span></div>
    <div class="guide-step"><strong>3. 人工发布</strong><span>检查账号、Page、素材和文案后，人工点击平台发布。</span></div>
    <div class="guide-step"><strong>4. 回填结果</strong><span>识别或填写帖子 URL，再写回状态并导出报告。</span></div>
  </section>
  <nav class="toolbar">
    <div class="toolbar-row">
      <input type="search" id="search" placeholder="搜索任务 ID / 账号 / 客户 / 产品 / 素材 / 错误">
      <select id="statusFilter"><option value="ALL">全部状态</option></select>
      <select id="platformFilter"><option value="ALL">全部平台</option></select>
      <select id="actionFilter"><option value="ALL">全部建议</option></select>
      <label class="selection"><input type="checkbox" id="selectVisible">选择当前列表</label>
    </div>
    <div class="toolbar-row">
      <button id="prepareSelected" class="primary">准备选中草稿</button>
      <button id="reload" class="soft">刷新投放表</button>
      <button id="exportSummary" class="soft">导出汇总 CSV</button>
      <button id="exportReport" class="soft">导出客户报告种子</button>
      <button id="exportReportPage" class="soft">生成客户报告网页</button>
    </div>
  </nav>
  <section id="deliverySync" class="preparation" role="status" aria-live="polite" hidden></section>
  <section id="preparation" class="preparation" role="status" aria-live="polite" hidden></section>
  <main>
    <div class="list-head">
      <strong>任务列表</strong>
      <span id="listHint"></span>
    </div>
    <div id="tasks"></div>
  </main>
  <div class="toast" id="toast"></div>
  <script>
    const state = {{ tasks: [], accounts: [], counts: {{}}, platforms: {{}}, sources: {{}}, preparation: {{}} }};
    let submittingPreparation = false;
    let syncingDelivery = false;
    let preparationTimer;
    let pollError = '';
    const tasksEl = document.querySelector('#tasks');
    const toastEl = document.querySelector('#toast');
    const searchEl = document.querySelector('#search');
    const statusFilter = document.querySelector('#statusFilter');
    const platformFilter = document.querySelector('#platformFilter');
    const actionFilter = document.querySelector('#actionFilter');
    const selectVisible = document.querySelector('#selectVisible');

    function esc(value) {{
      return String(value || '').replace(/[&<>"']/g, (ch) => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
      }}[ch]));
    }}

    function badgeClass(status) {{
      const key = String(status || '').toUpperCase();
      if (['PREPARED', 'PUBLISHED_MANUAL'].includes(key)) return 'ok';
      if (['FAILED', 'PARTIAL'].includes(key)) return 'bad';
      if (['REJECTED_MANUAL', 'SKIPPED'].includes(key)) return 'muted';
      return 'wait';
    }}

    function nextStep(task) {{
      const status = String(task.status || '').toUpperCase();
      if (status === 'READY') return '下一步：勾选这条任务，点击“准备选中草稿”。';
      if (status === 'PREPARED') return '下一步：到 TK / FB 页面检查草稿，确认后人工发布，再回来识别帖子 URL。';
      if (status === 'PUBLISHED_MANUAL') return '已发布：帖子链接已回填，可以导出汇总或生成客户报告。';
      if (status === 'FAILED' || status === 'PARTIAL') return '需要处理：先看错误和截图，修复后可加入重试队列。';
      if (status === 'REJECTED_MANUAL') return '已标记不发布：如需重试，可展开详情后加入重试队列。';
      return '请检查状态，必要时展开详情处理。';
    }}

    function labelText(value, fallback = '-') {{
      const text = String(value || '').trim();
      return text || fallback;
    }}

    function toast(message, bad = false) {{
      toastEl.textContent = message;
      toastEl.style.borderColor = bad ? '#fecdca' : '#9dd8bd';
      toastEl.classList.add('show');
      setTimeout(() => toastEl.classList.remove('show'), 2400);
    }}

    async function api(path, options = {{}}) {{
      const response = await fetch(path, {{
        ...options,
        headers: {{ 'Content-Type': 'application/json', ...(options.headers || {{}}) }}
      }});
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || 'request failed');
      return body;
    }}

    function fillSelect(select, values, label) {{
      const current = select.value || 'ALL';
      select.innerHTML = `<option value="ALL">全部${{label}}</option>` +
        values.map((value) => `<option value="${{esc(value)}}">${{esc(value)}}</option>`).join('');
      select.value = values.includes(current) ? current : 'ALL';
    }}

    function renderHeader() {{
      const sources = state.sources || {{}};
      document.querySelector('#sources').innerHTML = `
        <span>计划表：${{esc(sources.plan_csv)}}</span>
        <span>日志：${{esc(sources.log_jsonl)}}</span>
        <span>汇总：${{esc(sources.summary_csv)}}</span>
        <span>报告明细：${{esc(sources.customer_report_detail_csv)}}</span>
        <span>报告总览：${{esc(sources.customer_report_overview_csv)}}</span>
        <span>报告网页：${{esc(sources.customer_report_html)}}</span>
        <span>账号健康：${{esc(sources.account_health_csv)}}</span>
        <span>账号台账：${{esc(sources.account_ledger_csv)}}</span>
        <span>比特 API：${{esc(sources.bit_api)}}</span>
      `;
      document.querySelector('#stats').innerHTML = `
        <div class="stat"><strong>${{state.tasks.length}}</strong><span>任务</span></div>
        <div class="stat"><strong>${{state.platforms.tiktok || 0}}</strong><span>TikTok</span></div>
        <div class="stat"><strong>${{state.platforms.facebook || 0}}</strong><span>Facebook</span></div>
        <div class="stat"><strong>${{state.counts.PREPARED || 0}}</strong><span>待确认</span></div>
        <div class="stat"><strong>${{state.counts.PUBLISHED_MANUAL || 0}}</strong><span>已发布</span></div>
      `;
      fillSelect(statusFilter, Object.keys(state.counts).sort(), '状态');
      fillSelect(platformFilter, Object.keys(state.platforms).sort(), '平台');
      fillSelect(
        actionFilter,
        [...new Set(state.tasks.map((task) => String(task.error_action || 'NONE').toUpperCase()))].sort(),
        '建议'
      );
    }}

    function taskSearchText(task) {{
      return [
        task.publish_id, task.platform, task.status, task.account_key, task.profile_name,
        task.profile_id, task.client_id, task.product_id, task.title, task.media_path,
        task.tracking_url, task.post_url, task.platform_post_id,
        task.error_type, task.error_action, task.error_action_label, task.error_message, task.manual_note,
        task.candidate_count, task.candidate_sources, task.scanned_tab_count,
        task.scanner_error_count, task.scanner_errors
      ].join(' ').toLowerCase();
    }}

    function visibleTasks() {{
      const term = searchEl.value.trim().toLowerCase();
      const status = statusFilter.value;
      const platform = platformFilter.value;
      const action = actionFilter.value;
      return state.tasks.filter((task) => {{
        const statusOk = status === 'ALL' || String(task.status || 'UNKNOWN').toUpperCase() === status;
        const platformOk = platform === 'ALL' || String(task.platform || 'unknown').toLowerCase() === platform;
        const actionOk = action === 'ALL' || String(task.error_action || 'NONE').toUpperCase() === action;
        const searchOk = !term || taskSearchText(task).includes(term);
        return statusOk && platformOk && actionOk && searchOk;
      }});
    }}

    function fieldName(id, name) {{
      return `${{id}}-${{name}}`;
    }}

    function matchingAccounts(task) {{
      return state.accounts.filter((account) => !account.error && account.platform === task.platform);
    }}

    function preparationBusy() {{
      return submittingPreparation || Boolean(state.preparation.running);
    }}

    function renderPreparation() {{
      const job = state.preparation;
      const busy = preparationBusy();
      document.querySelector('#prepareSelected').disabled = busy || syncingDelivery;
      document.querySelector('#reload').textContent = syncingDelivery ? '正在刷新…' : '刷新投放表';
      document.querySelector('#prepareSelected').textContent = busy ? '正在准备草稿…' : '准备选中草稿';
      document.querySelectorAll('#tasks button, #tasks select, input[data-select], #selectVisible, #reload, #exportSummary, #exportReport, #exportReportPage')
        .forEach((el) => {{
          el.disabled = busy || syncingDelivery || el.dataset.locked === 'true';
        }});
      const panel = document.querySelector('#preparation');
      panel.hidden = !busy && !job.message;
      const elapsed = job.started_at ? Math.max(0, Math.floor((Date.now() - Date.parse(job.started_at)) / 1000)) : 0;
      const timing = busy ? ` · 已等待 ${{elapsed}} 秒` : '';
      panel.innerHTML = `${{busy ? '<progress aria-label="草稿准备中"></progress>' : ''}}
        <strong>${{esc(job.message || '正在提交任务，请稍候…')}}</strong>
        <span>${{job.total ? ` · 第 ${{job.index || 0}} / ${{job.total}} 条` : ''}} ${{esc(job.publish_id)}}${{timing}}</span>
        ${{pollError ? `<div class="assignment-error">${{esc(pollError)}}，正在重连，请勿重复启动。</div>` : ''}}`;
    }}

    function schedulePreparationPoll() {{
      clearTimeout(preparationTimer);
      if (state.preparation.running) preparationTimer = setTimeout(pollPreparation, 1000);
    }}

    async function pollPreparation() {{
      try {{
        state.preparation = await api('/api/prepare-status');
        pollError = '';
        renderPreparation();
        if (!state.preparation.running) {{
          await load();
          toast(state.preparation.message || '本批准备已结束', Boolean(state.preparation.error || state.preparation.needs_attention));
        }}
      }} catch (error) {{
        pollError = error.message || String(error);
        renderPreparation();
      }}
      schedulePreparationPoll();
    }}

    function renderTasks() {{
      const rows = visibleTasks();
      document.querySelector('#listHint').textContent = `当前显示 ${{rows.length}} / ${{state.tasks.length}} 条`;
      if (!rows.length) {{
        tasksEl.innerHTML = '<div class="empty-shot">没有匹配任务</div>';
        return;
      }}
      tasksEl.innerHTML = rows.map((task) => {{
        const shot = task.screenshot_url
          ? `<a href="${{esc(task.screenshot_url)}}" target="_blank"><img src="${{esc(task.screenshot_url)}}" alt="screenshot"></a>`
          : '<div class="empty-shot">No screenshot</div>';
        const status = task.status || 'UNKNOWN';
        const publishId = esc(task.publish_id);
        const operator = esc(task.manual_operator || '');
        const editable = ['READY', 'FAILED', 'PARTIAL'].includes(String(status).toUpperCase());
        const accounts = matchingAccounts(task);
        return `
          <article class="task" data-id="${{publishId}}">
            <div class="shot">${{shot}}</div>
            <div class="task-main">
              <div class="task-head">
                <input class="task-select" type="checkbox" data-select="${{publishId}}" data-locked="${{!editable}}" ${{editable ? '' : 'disabled'}}>
                <span class="badge ${{badgeClass(status)}}">${{esc(status)}}</span>
                <span>${{esc(task.platform)}}</span>
                <span>${{esc(task.content_type)}}</span>
                <span>${{esc(task.facebook_content_mode)}}</span>
                <span>${{esc(task.duration_seconds || '')}}s</span>
              </div>
              <h2>${{publishId}}</h2>
              <p class="title">${{esc(task.title)}}</p>
              <div class="meta">
                <span>账号：${{esc(task.account_key || '未分配')}}</span>
                <span>客户：${{esc(task.client_id)}}</span>
                <span>产品：${{esc(task.product_id)}}</span>
                <span>素材：${{esc(labelText(task.media_path))}}</span>
              </div>
              <div class="assignment">
                <label>目标账号
                  <select name="${{fieldName(task.publish_id, 'account_key')}}" data-assignment="${{publishId}}" data-locked="${{!editable}}" ${{editable ? '' : 'disabled'}}>
                    <option value="">${{accounts.length ? '请选择目标账号' : '台账暂无可用的本平台账号'}}</option>
                    ${{accounts.map((account) => `<option value="${{esc(account.account_key)}}" ${{account.account_key === task.account_key ? 'selected' : ''}}>${{esc(account.account_key)}} · ${{esc(account.profile_name || account.profile_id)}}</option>`).join('')}}
                  </select>
                </label>
                <button class="soft" data-action="assign" data-id="${{publishId}}" data-locked="${{!editable}}" ${{editable ? '' : 'disabled'}}>保存分配</button>
                <span class="assignment-window" data-window="${{publishId}}">对应窗口：${{esc(task.profile_name || '未命名')}} / ${{esc(task.profile_id || '未分配')}}</span>
              </div>
              ${{editable && task.assignment_error ? `<div class="assignment-error">${{esc(task.assignment_error)}}</div>` : ''}}
              <div class="next-step">${{esc(nextStep(task))}}</div>
              <div class="quick-actions">
                <button class="soft" data-action="detect" data-id="${{publishId}}">识别帖子 URL</button>
                <button class="primary" data-action="backfill" data-id="${{publishId}}">写回状态</button>
                <button class="soft" data-action="ready" data-id="${{publishId}}">加入重试队列</button>
                <button class="danger" data-action="reject" data-id="${{publishId}}">不发布</button>
              </div>
              <details class="task-details">
                <summary>展开详情 / 回填 / 账号健康</summary>
                <div class="paths">
                  <div>窗口：${{esc(task.profile_name)}} / 窗口ID：${{esc(task.profile_id)}}</div>
                  <div>短链：${{esc(task.tracking_url)}}</div>
                  <div>任务文案：${{esc(task.caption)}}</div>
                  <div>任务标签：${{esc(task.hashtags)}}</div>
                  <div>帖子：${{esc(task.post_url)}}</div>
                  <div>帖子ID：${{esc(task.platform_post_id)}}</div>
                  <div>发布时间：${{esc(task.published_at)}}</div>
                  <div>截图：${{esc(task.screenshot)}}</div>
                  <div>上传：${{esc(task.uploaded)}} / 文案：${{esc(task.caption_filled)}} / 健康：${{esc(task.account_health_status || '')}}</div>
                  <div>错误：${{esc(task.error_type)}} ${{esc(task.error_action_label || task.error_action)}} ${{esc(task.error_message)}}</div>
                  <div>诊断：候选 ${{esc(task.candidate_count || '')}} / ${{esc(task.candidate_sources || '')}}</div>
                  <div>扫描：${{esc(task.scanned_tab_count || '')}} 页签 / ${{esc(task.scanner_error_count || '')}} 错误</div>
                  <div>${{esc(task.scanner_errors || '')}}</div>
                </div>
                <div class="forms">
                  <section>
                    <div class="form-grid">
                      <label>状态
                        <select name="${{fieldName(task.publish_id, 'status')}}">
                          ${{
                            ['PUBLISHED_MANUAL', 'REJECTED_MANUAL', 'PREPARED', 'FAILED', 'READY']
                              .map((value) => `<option value="${{value}}" ${{value === status ? 'selected' : ''}}>${{value}}</option>`)
                              .join('')
                          }}
                        </select>
                      </label>
                      <label>操作人<input name="${{fieldName(task.publish_id, 'operator')}}" value="${{operator}}"></label>
                      <label class="wide">帖子 URL<input name="${{fieldName(task.publish_id, 'post_url')}}" value="${{esc(task.post_url)}}"></label>
                      <label>帖子 ID<input name="${{fieldName(task.publish_id, 'platform_post_id')}}" value="${{esc(task.platform_post_id)}}"></label>
                      <label>发布时间<input name="${{fieldName(task.publish_id, 'published_at')}}" value="${{esc(task.published_at || '')}}" placeholder="YYYY-MM-DDTHH:MM:SS"></label>
                      <label>错误类型<input name="${{fieldName(task.publish_id, 'error_type')}}" value="${{esc(task.error_type)}}"></label>
                      <label>处理建议<input name="${{fieldName(task.publish_id, 'error_action')}}" value="${{esc(task.error_action)}}"></label>
                      <label>建议说明<input name="${{fieldName(task.publish_id, 'error_action_label')}}" value="${{esc(task.error_action_label)}}"></label>
                      <label class="wide">备注<textarea name="${{fieldName(task.publish_id, 'manual_note')}}">${{esc(task.manual_note)}}</textarea></label>
                      <label class="wide">错误信息<textarea name="${{fieldName(task.publish_id, 'error_message')}}">${{esc(task.error_message)}}</textarea></label>
                    </div>
                  </section>
                  <section>
                    <div class="form-grid">
                      <label>健康状态
                        <select name="${{fieldName(task.publish_id, 'health_status')}}">
                          <option value="OK">OK</option>
                          <option value="WATCH">WATCH</option>
                          <option value="BLOCKED">BLOCKED</option>
                          <option value="LOGIN_REQUIRED">LOGIN_REQUIRED</option>
                          <option value="PROXY_ISSUE">PROXY_ISSUE</option>
                          <option value="PAGE_ACCESS_ISSUE">PAGE_ACCESS_ISSUE</option>
                        </select>
                      </label>
                      <label>问题类型<input name="${{fieldName(task.publish_id, 'issue_type')}}" value="${{esc(task.account_health_issue || '')}}"></label>
                      <label class="wide">账号备注<textarea name="${{fieldName(task.publish_id, 'health_note')}}">${{esc(task.account_health_note || '')}}</textarea></label>
                    </div>
                    <div class="actions" style="margin-top:8px">
                      <button class="soft" data-action="health" data-id="${{publishId}}">记录账号健康</button>
                    </div>
                  </section>
                </div>
              </details>
            </div>
          </article>
        `;
      }}).join('');
      renderPreparation();
    }}

    function value(id, name) {{
      const el = document.querySelector(`[name="${{CSS.escape(fieldName(id, name))}}"]`);
      return el ? el.value.trim() : '';
    }}

    function setValue(id, name, text) {{
      const el = document.querySelector(`[name="${{CSS.escape(fieldName(id, name))}}"]`);
      if (el) el.value = text || '';
    }}

    function detectionFailureMessage(result) {{
      const type = String(result.error_type || result.detection_status || 'POST_URL_NOT_FOUND');
      let message = result.error_message || '没有在当前标签页识别到公开帖子 URL';
      if (Array.isArray(result.conflicting_post_ids) && result.conflicting_post_ids.length) {{
        message += ` 冲突 ID：${{result.conflicting_post_ids.join(', ')}}`;
      }}
      return `${{type}}：${{message}}`;
    }}

    async function submitBackfill(id, forcedStatus = '') {{
      const status = forcedStatus || value(id, 'status');
      const body = {{
        publish_id: id,
        status,
        post_url: value(id, 'post_url'),
        platform_post_id: value(id, 'platform_post_id'),
        published_at: value(id, 'published_at'),
        manual_operator: value(id, 'operator'),
        manual_note: value(id, 'manual_note'),
        error_type: value(id, 'error_type'),
        error_action: value(id, 'error_action'),
        error_action_label: value(id, 'error_action_label'),
        error_message: value(id, 'error_message')
      }};
      await api('/api/backfill', {{ method: 'POST', body: JSON.stringify(body) }});
      toast(`已写回 ${{id}} -> ${{status}}`);
      await load();
    }}

    async function detectPostUrl(id) {{
      const task = state.tasks.find((item) => item.publish_id === id) || {{}};
      const body = {{
        publish_id: id,
        platform: task.platform,
        account_key: task.account_key,
        profile_id: task.profile_id
      }};
      const response = await api('/api/detect-post-url', {{ method: 'POST', body: JSON.stringify(body) }});
      const result = response.result || {{}};
      if (!result.detected) {{
        toast(detectionFailureMessage(result), true);
        return;
      }}
      setValue(id, 'status', 'PUBLISHED_MANUAL');
      setValue(id, 'post_url', result.post_url || '');
      setValue(id, 'platform_post_id', result.platform_post_id || '');
      setValue(id, 'published_at', result.published_at || '');
      const note = value(id, 'manual_note');
      const detectedNote = `自动识别：${{result.source || ''}} tab=${{result.tab_index || ''}}`;
      setValue(id, 'manual_note', note ? `${{note}}\n${{detectedNote}}` : detectedNote);
      toast(`已识别帖子 URL：${{result.platform_post_id || result.post_url}}`);
    }}

    async function submitHealth(id) {{
      const task = state.tasks.find((item) => item.publish_id === id) || {{}};
      const body = {{
        publish_id: id,
        account_key: task.account_key,
        platform: task.platform,
        profile_name: task.profile_name,
        health_status: value(id, 'health_status'),
        issue_type: value(id, 'issue_type'),
        note: value(id, 'health_note'),
        operator: value(id, 'operator')
      }};
      await api('/api/account-health', {{ method: 'POST', body: JSON.stringify(body) }});
      toast(`已记录账号健康：${{task.account_key || id}}`);
      await load();
    }}

    async function load() {{
      const data = await api('/api/tasks');
      state.tasks = data.tasks || [];
      state.accounts = data.accounts || [];
      state.counts = data.counts || {{}};
      state.platforms = data.platforms || {{}};
      state.sources = data.sources || {{}};
      state.preparation = data.preparation || {{}};
      const sync = data.delivery_sync || {{}};
      const syncPanel = document.querySelector('#deliverySync');
      syncPanel.hidden = sync.added === undefined;
      syncPanel.innerHTML = sync.added === undefined ? '' : `<strong>投放表已刷新：新增 ${{sync.added}} 条任务，更新 ${{sync.updated}} 条文案</strong>
        ${{(sync.warnings || []).map((warning) => `<div class="assignment-error">${{esc(warning)}}</div>`).join('')}}`;
      renderHeader();
      renderTasks();
      renderPreparation();
      schedulePreparationPoll();
    }}

    document.addEventListener('click', async (event) => {{
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      const id = button.dataset.id;
      try {{
        if (button.dataset.action === 'assign') {{
          await api('/api/assign-account', {{ method: 'POST', body: JSON.stringify({{ publish_id: id, account_key: value(id, 'account_key') }}) }});
          await load();
          toast('目标账号与窗口分配已保存');
        }}
        if (button.dataset.action === 'backfill') await submitBackfill(id);
        if (button.dataset.action === 'detect') await detectPostUrl(id);
        if (button.dataset.action === 'ready') await submitBackfill(id, 'READY');
        if (button.dataset.action === 'reject') await submitBackfill(id, 'REJECTED_MANUAL');
        if (button.dataset.action === 'health') await submitHealth(id);
      }} catch (error) {{
        toast(error.message || String(error), true);
      }}
    }});
    document.addEventListener('change', (event) => {{
      const select = event.target.closest('select[data-assignment]');
      if (!select) return;
      const task = state.tasks.find((item) => item.publish_id === select.dataset.assignment);
      const account = matchingAccounts(task).find((item) => item.account_key === select.value);
      const label = document.querySelector(`[data-window="${{CSS.escape(task.publish_id)}}"]`);
      label.textContent = account ? `对应窗口：${{account.profile_name || '未命名'}} / ${{account.profile_id}}（待保存）` : '请选择目标账号';
    }});
    document.querySelector('#reload').addEventListener('click', async () => {{
      if (preparationBusy() || syncingDelivery) return;
      syncingDelivery = true;
      renderPreparation();
      try {{
        const result = await api('/api/refresh-delivery', {{ method: 'POST', body: '{{}}' }});
        await load();
        toast(`刷新完成：新增 ${{result.added}} 条任务，更新 ${{result.updated}} 条文案`, Boolean(result.warnings.length));
      }} catch (error) {{
        toast(error.message || String(error), true);
      }} finally {{
        syncingDelivery = false;
        renderPreparation();
      }}
    }});
    selectVisible.addEventListener('change', () => {{
      document.querySelectorAll('input[data-select]:not(:disabled)').forEach((checkbox) => {{
        checkbox.checked = selectVisible.checked;
      }});
    }});
    document.querySelector('#prepareSelected').addEventListener('click', async () => {{
      if (preparationBusy()) return;
      const publishIds = [...document.querySelectorAll('input[data-select]:checked')]
        .map((checkbox) => checkbox.dataset.select)
        .filter(Boolean);
      if (!publishIds.length) {{
        toast('请先选择 READY、失败或部分成功任务', true);
        return;
      }}
      const selected = state.tasks.filter((task) => publishIds.includes(task.publish_id));
      if (selected.some((task) => value(task.publish_id, 'account_key') !== task.account_key || task.assignment_error)) {{
        toast('请先选择并保存每条任务的目标账号和窗口', true);
        return;
      }}
      submittingPreparation = true;
      renderPreparation();
      try {{
        state.preparation = await api('/api/prepare', {{
          method: 'POST',
          body: JSON.stringify({{ publish_ids: publishIds }})
        }});
        await load();
      }} catch (error) {{
        // A dropped response does not imply that the server stopped the batch.
        try {{ state.preparation = await api('/api/prepare-status'); }}
        catch (_) {{ state.preparation = {{ running: true, message: '连接中断，正在确认任务状态' }}; }}
        toast(error.message || String(error), true);
      }} finally {{
        submittingPreparation = false;
        renderPreparation();
        schedulePreparationPoll();
        if (!state.preparation.running) await load();
      }}
    }});
    document.querySelector('#exportSummary').addEventListener('click', async () => {{
      try {{
        const result = await api('/api/export-summary', {{ method: 'POST', body: JSON.stringify({{ include_history: false }}) }});
        toast(`已导出汇总：${{result.rows}} 行`);
        await load();
      }} catch (error) {{
        toast(error.message || String(error), true);
      }}
    }});
    document.querySelector('#exportReport').addEventListener('click', async () => {{
      try {{
        const result = await api('/api/export-customer-report', {{ method: 'POST', body: JSON.stringify({{}}) }});
        toast(`已导出报告种子：明细 ${{result.detail_rows}} 行，总览 ${{result.overview_rows}} 行`);
        await load();
      }} catch (error) {{
        toast(error.message || String(error), true);
      }}
    }});
    document.querySelector('#exportReportPage').addEventListener('click', async () => {{
      try {{
        const result = await api('/api/export-customer-report-page', {{ method: 'POST', body: JSON.stringify({{}}) }});
        toast(`已生成客户报告网页：${{result.customer_report_html || ''}}`);
        if (result.customer_report_url) window.open(result.customer_report_url, '_blank');
        await load();
      }} catch (error) {{
        toast(error.message || String(error), true);
      }}
    }});
    searchEl.addEventListener('input', renderTasks);
    statusFilter.addEventListener('change', renderTasks);
    platformFilter.addEventListener('change', renderTasks);
    actionFilter.addEventListener('change', renderTasks);
    load().catch((error) => toast(error.message, true));
  </script>
</body>
</html>"""


class WorkbenchHandler(BaseHTTPRequestHandler):
    state: WorkbenchState

    def log_message(self, format: str, *args: Any) -> None:
        if sys.stderr:
            sys.stderr.write("[workbench] " + format % args + "\n")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                text_response(self, render_page())
                return
            if parsed.path == "/api/tasks":
                json_response(self, self.state.snapshot())
                return
            if parsed.path == "/api/prepare-status":
                json_response(self, self.state.preparation_status())
                return
            if parsed.path == "/artifact":
                params = parse_qs(parsed.query)
                artifact = self.state.resolve_artifact(params.get("path", [""])[0])
                content_type = mimetypes.guess_type(str(artifact))[0] or "application/octet-stream"
                data = artifact.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            json_response(self, {"error": "not found"}, status=404)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, status=400)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = read_json_body(self)
            if parsed.path == "/api/backfill":
                json_response(self, self.state.backfill(body))
                return
            if parsed.path == "/api/account-health":
                json_response(self, self.state.account_health(body))
                return
            if parsed.path == "/api/detect-post-url":
                json_response(self, self.state.detect_post_url(body))
                return
            if parsed.path == "/api/prepare":
                json_response(self, self.state.prepare_tasks(body))
                return
            if parsed.path == "/api/refresh-delivery":
                json_response(self, self.state.refresh_delivery())
                return
            if parsed.path == "/api/assign-account":
                json_response(self, self.state.assign_account(body))
                return
            if parsed.path == "/api/export-summary":
                include_history = bool(body.get("include_history"))
                json_response(self, self.state.export_summary(include_history=include_history))
                return
            if parsed.path == "/api/export-customer-report":
                json_response(self, self.state.export_customer_report())
                return
            if parsed.path == "/api/export-customer-report-page":
                json_response(self, self.state.export_customer_report_page())
                return
            json_response(self, {"error": "not found"}, status=404)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, status=400)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local RPA confirmation workbench")
    parser.add_argument("--plan-csv", required=True, help="publish_plan.csv path")
    parser.add_argument("--log-jsonl", help="publish_logs.jsonl path")
    parser.add_argument("--summary-csv", help="publish_summary.csv path")
    parser.add_argument("--customer-report-detail-csv", help="Customer report detail seed CSV path")
    parser.add_argument("--customer-report-overview-csv", help="Customer report overview CSV path")
    parser.add_argument("--customer-report-html", help="Customer report HTML path")
    parser.add_argument("--account-health-csv", help="Account health CSV path")
    parser.add_argument("--account-ledger", help="Account ledger CSV path")
    parser.add_argument("--bit-api", default=DEFAULT_BIT_API, help=f"BitBrowser local API URL. Default: {DEFAULT_BIT_API}")
    parser.add_argument("--operator", default="", help="Default manual operator name")
    parser.add_argument("--host", default=DEFAULT_HOST, help="HTTP bind host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="HTTP port")
    parser.add_argument("--open-browser", action="store_true", help="Open the workbench URL in the default browser")
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> WorkbenchConfig:
    plan_csv = Path(args.plan_csv).expanduser().resolve()
    if not plan_csv.is_file():
        raise SystemExit(f"publish_plan.csv not found: {plan_csv}")
    log_jsonl = Path(args.log_jsonl).expanduser().resolve() if args.log_jsonl else plan_csv.parent / DEFAULT_JSONL
    summary_csv = Path(args.summary_csv).expanduser().resolve() if args.summary_csv else plan_csv.parent / DEFAULT_SUMMARY
    customer_report_detail_csv = (
        Path(args.customer_report_detail_csv).expanduser().resolve()
        if args.customer_report_detail_csv
        else summary_csv.parent / DEFAULT_CUSTOMER_REPORT_DETAIL
    )
    customer_report_overview_csv = (
        Path(args.customer_report_overview_csv).expanduser().resolve()
        if args.customer_report_overview_csv
        else summary_csv.parent / DEFAULT_CUSTOMER_REPORT_OVERVIEW
    )
    customer_report_html = (
        Path(args.customer_report_html).expanduser().resolve()
        if args.customer_report_html
        else customer_report_detail_csv.parent / DEFAULT_CUSTOMER_REPORT_HTML
    )
    account_health_csv = (
        Path(args.account_health_csv).expanduser().resolve()
        if args.account_health_csv
        else plan_csv.parent / DEFAULT_ACCOUNT_HEALTH
    )
    account_ledger_csv = (
        Path(args.account_ledger).expanduser().resolve()
        if args.account_ledger
        else _discover_file_upwards(plan_csv.parent, (DEFAULT_ACCOUNT_LEDGER_FILENAME,))
        or plan_csv.parent / DEFAULT_ACCOUNT_LEDGER_FILENAME
    )
    return WorkbenchConfig(
        plan_csv=plan_csv,
        log_jsonl=log_jsonl,
        summary_csv=summary_csv,
        customer_report_detail_csv=customer_report_detail_csv,
        customer_report_overview_csv=customer_report_overview_csv,
        customer_report_html=customer_report_html,
        account_health_csv=account_health_csv,
        account_ledger_csv=account_ledger_csv,
        bit_api=args.bit_api,
        operator=args.operator,
        open_browser=args.open_browser,
    )


def run_server(args: argparse.Namespace) -> int:
    config = build_config(args)
    state = WorkbenchState(config)

    class Handler(WorkbenchHandler):
        pass

    Handler.state = state
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    safe_print(f"RPA confirmation workbench: {url}")
    safe_print(f"Plan CSV: {config.plan_csv}")
    safe_print("Press Ctrl+C to stop.")
    if config.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        safe_print("\nWorkbench stopped.")
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_server(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
