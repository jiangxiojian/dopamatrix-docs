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
import webbrowser
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
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
    append_jsonl_log,
    connect_browser_context,
    detect_post_url_in_context,
    extract_platform_post_id,
    load_account_ledger,
    normalize_platform_name,
    select_account_entry,
    update_publish_plan_row,
    write_summary_csv,
)
from rpa_report_export import (  # noqa: E402
    DEFAULT_DETAIL as DEFAULT_CUSTOMER_REPORT_DETAIL,
    DEFAULT_OVERVIEW as DEFAULT_CUSTOMER_REPORT_OVERVIEW,
    export_customer_report as write_customer_report_seed,
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


@dataclass
class WorkbenchConfig:
    plan_csv: Path
    log_jsonl: Path
    summary_csv: Path
    customer_report_detail_csv: Path
    customer_report_overview_csv: Path
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
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


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
        self.allowed_roots = [
            Path.cwd().resolve(),
            config.plan_csv.parent.resolve(),
            config.log_jsonl.parent.resolve(),
            config.summary_csv.parent.resolve(),
            config.customer_report_detail_csv.parent.resolve(),
            config.customer_report_overview_csv.parent.resolve(),
            config.account_health_csv.parent.resolve(),
            config.account_ledger_csv.parent.resolve(),
        ]

    def all_rows(self) -> list[dict[str, str]]:
        plan_rows = [normalize_plan_row(row, self.config.plan_csv) for row in read_csv_rows(self.config.plan_csv)]
        summary_rows = [normalize_summary_row(row) for row in read_csv_rows(self.config.summary_csv)]
        if not summary_rows:
            summary_rows = latest_jsonl_rows(read_jsonl(self.config.log_jsonl))
        rows = merge_rows(plan_rows, summary_rows)
        health_index = latest_health_by_account(read_account_health(self.config.account_health_csv))
        for row in rows:
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
                "account_health_csv": str(self.config.account_health_csv),
                "account_ledger_csv": str(self.config.account_ledger_csv),
                "bit_api": self.config.bit_api,
            },
            "counts": dict(counts),
            "platforms": dict(platforms),
            "tasks": rows,
            "account_health": read_account_health(self.config.account_health_csv)[-100:],
        }

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
                "error_message": error_message,
                "finished_at": checked_at,
                "workbench": True,
            },
        }
        append_jsonl_log(self.config.log_jsonl, payload)
        return {"updated": updated, "task": self.find_task(publish_id)}

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
            result["detection_status"] = "POST_URL_DETECTED" if result.get("detected") else "POST_URL_NOT_FOUND"
            result["status"] = task.get("status", "") or "PREPARED"
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
            if result.get("detected"):
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

    def export_summary(self, include_history: bool = False) -> dict[str, Any]:
        rows = write_summary_csv(self.config.log_jsonl, self.config.summary_csv, include_history=include_history)
        return {"summary_csv": str(self.config.summary_csv), "rows": len(rows)}

    def export_customer_report(self) -> dict[str, Any]:
        summary_rows = write_summary_csv(self.config.log_jsonl, self.config.summary_csv, include_history=False)
        result = write_customer_report_seed(
            self.config.summary_csv,
            self.config.customer_report_detail_csv,
            self.config.customer_report_overview_csv,
        )
        result["summary_rows"] = len(summary_rows)
        return result

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
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: var(--ink); background: #fff; }}
    header {{ padding: 16px 22px; border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 2; background: #fff; }}
    h1 {{ margin: 0 0 10px; font-size: 22px; }}
    .source {{ display: grid; gap: 4px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }}
    .stats, .toolbar, .meta, .actions {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .stats {{ margin-top: 12px; }}
    .stat {{ min-width: 110px; padding: 8px 10px; border: 1px solid var(--line); background: var(--panel); }}
    .stat strong {{ display: block; font-size: 19px; }}
    .toolbar {{ padding: 12px 22px; border-bottom: 1px solid var(--line); }}
    input, select, textarea, button {{ font: inherit; }}
    input, select, textarea {{ border: 1px solid var(--line); padding: 8px; background: #fff; color: var(--ink); }}
    input[type="search"] {{ width: min(520px, 100%); }}
    button {{ border: 1px solid var(--line); background: #fff; color: var(--ink); padding: 8px 10px; cursor: pointer; }}
    button.primary {{ border-color: var(--blue); background: var(--blue); color: #fff; }}
    button.soft {{ border-color: #b7cffd; background: var(--soft-blue); color: #174ea6; }}
    button.danger {{ border-color: #fecdca; color: var(--bad); background: #fff1f3; }}
    main {{ padding: 16px 22px 36px; display: grid; gap: 14px; }}
    .task {{ display: grid; grid-template-columns: 260px 1fr; border: 1px solid var(--line); background: #fff; min-height: 220px; }}
    .shot {{ border-right: 1px solid var(--line); background: #f2f5f7; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
    .shot img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
    .empty-shot {{ color: var(--muted); font-size: 13px; }}
    .task-main {{ padding: 14px; min-width: 0; }}
    .task-head {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; color: var(--muted); font-size: 13px; }}
    .badge {{ border: 1px solid var(--line); padding: 3px 7px; font-weight: 700; }}
    .badge.ok {{ color: var(--ok); border-color: #9dd8bd; background: #ecfdf3; }}
    .badge.bad {{ color: var(--bad); border-color: #fecdca; background: #fff1f3; }}
    .badge.wait {{ color: var(--wait); border-color: #fedf89; background: #fffaeb; }}
    .badge.muted {{ color: #475467; border-color: #d0d5dd; background: #f2f4f7; }}
    h2 {{ margin: 8px 0 6px; font-size: 18px; overflow-wrap: anywhere; }}
    .title {{ margin: 0 0 10px; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 10px; }}
    .paths, .error {{ color: var(--muted); font-size: 12px; display: grid; gap: 3px; overflow-wrap: anywhere; }}
    .error {{ color: var(--bad); margin-top: 6px; }}
    .forms {{ display: grid; grid-template-columns: minmax(260px, 1fr) minmax(260px, 1fr); gap: 12px; margin-top: 12px; border-top: 1px solid var(--line); padding-top: 12px; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(120px, 1fr)); gap: 8px; }}
    .form-grid label {{ display: grid; gap: 4px; font-size: 12px; color: var(--muted); }}
    .form-grid label.wide {{ grid-column: 1 / -1; }}
    textarea {{ min-height: 70px; resize: vertical; }}
    .toast {{ position: fixed; right: 18px; bottom: 18px; max-width: min(420px, calc(100vw - 36px)); padding: 12px 14px; border: 1px solid var(--line); background: #fff; box-shadow: 0 12px 32px rgba(16, 24, 40, .18); display: none; }}
    .toast.show {{ display: block; }}
    @media (max-width: 900px) {{
      header, .toolbar, main {{ padding-left: 12px; padding-right: 12px; }}
      .task {{ grid-template-columns: 1fr; }}
      .shot {{ height: 220px; border-right: 0; border-bottom: 1px solid var(--line); }}
      .forms {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>RPA 确认工作台</h1>
    <div class="source" id="sources"></div>
    <div class="stats" id="stats"></div>
  </header>
  <nav class="toolbar">
    <input type="search" id="search" placeholder="搜索 publish_id / 账号 / 客户 / 产品 / 素材 / 错误">
    <select id="statusFilter"><option value="ALL">全部状态</option></select>
    <select id="platformFilter"><option value="ALL">全部平台</option></select>
    <button id="reload" class="soft">刷新</button>
    <button id="exportSummary" class="soft">导出汇总 CSV</button>
    <button id="exportReport" class="soft">导出客户报告种子</button>
  </nav>
  <main id="tasks"></main>
  <div class="toast" id="toast"></div>
  <script>
    const state = {{ tasks: [], counts: {{}}, platforms: {{}}, sources: {{}} }};
    const tasksEl = document.querySelector('#tasks');
    const toastEl = document.querySelector('#toast');
    const searchEl = document.querySelector('#search');
    const statusFilter = document.querySelector('#statusFilter');
    const platformFilter = document.querySelector('#platformFilter');

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
        <span>账号健康：${{esc(sources.account_health_csv)}}</span>
        <span>账号台账：${{esc(sources.account_ledger_csv)}}</span>
        <span>比特 API：${{esc(sources.bit_api)}}</span>
      `;
      document.querySelector('#stats').innerHTML = `
        <div class="stat"><strong>${{state.tasks.length}}</strong>任务</div>
        <div class="stat"><strong>${{state.platforms.tiktok || 0}}</strong>TikTok</div>
        <div class="stat"><strong>${{state.platforms.facebook || 0}}</strong>Facebook</div>
        <div class="stat"><strong>${{state.counts.PREPARED || 0}}</strong>待确认</div>
        <div class="stat"><strong>${{state.counts.PUBLISHED_MANUAL || 0}}</strong>已发布</div>
      `;
      fillSelect(statusFilter, Object.keys(state.counts).sort(), '状态');
      fillSelect(platformFilter, Object.keys(state.platforms).sort(), '平台');
    }}

    function taskSearchText(task) {{
      return [
        task.publish_id, task.platform, task.status, task.account_key, task.profile_name,
        task.profile_id, task.client_id, task.product_id, task.title, task.media_path,
        task.tracking_url, task.post_url, task.platform_post_id,
        task.error_type, task.error_message, task.manual_note
      ].join(' ').toLowerCase();
    }}

    function visibleTasks() {{
      const term = searchEl.value.trim().toLowerCase();
      const status = statusFilter.value;
      const platform = platformFilter.value;
      return state.tasks.filter((task) => {{
        const statusOk = status === 'ALL' || String(task.status || 'UNKNOWN').toUpperCase() === status;
        const platformOk = platform === 'ALL' || String(task.platform || 'unknown').toLowerCase() === platform;
        const searchOk = !term || taskSearchText(task).includes(term);
        return statusOk && platformOk && searchOk;
      }});
    }}

    function fieldName(id, name) {{
      return `${{id}}-${{name}}`;
    }}

    function renderTasks() {{
      const rows = visibleTasks();
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
        return `
          <article class="task" data-id="${{publishId}}">
            <div class="shot">${{shot}}</div>
            <div class="task-main">
              <div class="task-head">
                <span class="badge ${{badgeClass(status)}}">${{esc(status)}}</span>
                <span>${{esc(task.platform)}}</span>
                <span>${{esc(task.content_type)}}</span>
                <span>${{esc(task.facebook_content_mode)}}</span>
                <span>${{esc(task.duration_seconds || '')}}s</span>
              </div>
              <h2>${{publishId}}</h2>
              <p class="title">${{esc(task.title)}}</p>
              <div class="meta">
                <span>账号：${{esc(task.account_key)}}</span>
                <span>窗口：${{esc(task.profile_name)}}</span>
                <span>窗口ID：${{esc(task.profile_id)}}</span>
                <span>客户：${{esc(task.client_id)}}</span>
                <span>产品：${{esc(task.product_id)}}</span>
                <span>上传：${{esc(task.uploaded)}}</span>
                <span>文案：${{esc(task.caption_filled)}}</span>
                <span>健康：${{esc(task.account_health_status || '')}}</span>
              </div>
              <div class="paths">
                <div>短链：${{esc(task.tracking_url)}}</div>
                <div>帖子：${{esc(task.post_url)}}</div>
                <div>帖子ID：${{esc(task.platform_post_id)}}</div>
                <div>发布时间：${{esc(task.published_at)}}</div>
                <div>素材：${{esc(task.media_path)}}</div>
                <div>截图：${{esc(task.screenshot)}}</div>
                <div>错误：${{esc(task.error_type)}} ${{esc(task.error_message)}}</div>
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
                    <label class="wide">备注<textarea name="${{fieldName(task.publish_id, 'manual_note')}}">${{esc(task.manual_note)}}</textarea></label>
                    <label class="wide">错误信息<textarea name="${{fieldName(task.publish_id, 'error_message')}}">${{esc(task.error_message)}}</textarea></label>
                  </div>
                  <div class="actions" style="margin-top:8px">
                    <button class="soft" data-action="detect" data-id="${{publishId}}">识别帖子 URL</button>
                    <button class="primary" data-action="backfill" data-id="${{publishId}}">写回状态</button>
                    <button class="soft" data-action="ready" data-id="${{publishId}}">加入重试队列</button>
                    <button class="danger" data-action="reject" data-id="${{publishId}}">不发布</button>
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
            </div>
          </article>
        `;
      }}).join('');
    }}

    function value(id, name) {{
      const el = document.querySelector(`[name="${{CSS.escape(fieldName(id, name))}}"]`);
      return el ? el.value.trim() : '';
    }}

    function setValue(id, name, text) {{
      const el = document.querySelector(`[name="${{CSS.escape(fieldName(id, name))}}"]`);
      if (el) el.value = text || '';
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
        toast('没有在当前标签页识别到公开帖子 URL', true);
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
      state.counts = data.counts || {{}};
      state.platforms = data.platforms || {{}};
      state.sources = data.sources || {{}};
      renderHeader();
      renderTasks();
    }}

    document.addEventListener('click', async (event) => {{
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      const id = button.dataset.id;
      try {{
        if (button.dataset.action === 'backfill') await submitBackfill(id);
        if (button.dataset.action === 'detect') await detectPostUrl(id);
        if (button.dataset.action === 'ready') await submitBackfill(id, 'READY');
        if (button.dataset.action === 'reject') await submitBackfill(id, 'REJECTED_MANUAL');
        if (button.dataset.action === 'health') await submitHealth(id);
      }} catch (error) {{
        toast(error.message || String(error), true);
      }}
    }});
    document.querySelector('#reload').addEventListener('click', () => load().catch((error) => toast(error.message, true)));
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
    searchEl.addEventListener('input', renderTasks);
    statusFilter.addEventListener('change', renderTasks);
    platformFilter.addEventListener('change', renderTasks);
    load().catch((error) => toast(error.message, true));
  </script>
</body>
</html>"""


class WorkbenchHandler(BaseHTTPRequestHandler):
    state: WorkbenchState

    def log_message(self, format: str, *args: Any) -> None:
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
            if parsed.path == "/api/export-summary":
                include_history = bool(body.get("include_history"))
                json_response(self, self.state.export_summary(include_history=include_history))
                return
            if parsed.path == "/api/export-customer-report":
                json_response(self, self.state.export_customer_report())
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
    account_health_csv = (
        Path(args.account_health_csv).expanduser().resolve()
        if args.account_health_csv
        else plan_csv.parent / DEFAULT_ACCOUNT_HEALTH
    )
    account_ledger_csv = (
        Path(args.account_ledger).expanduser().resolve()
        if args.account_ledger
        else plan_csv.parent / DEFAULT_ACCOUNT_LEDGER_FILENAME
    )
    return WorkbenchConfig(
        plan_csv=plan_csv,
        log_jsonl=log_jsonl,
        summary_csv=summary_csv,
        customer_report_detail_csv=customer_report_detail_csv,
        customer_report_overview_csv=customer_report_overview_csv,
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
    print(f"RPA confirmation workbench: {url}")
    print(f"Plan CSV: {config.plan_csv}")
    print("Press Ctrl+C to stop.")
    if config.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWorkbench stopped.")
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_server(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
