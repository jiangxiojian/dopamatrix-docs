"""
BitBrowser assisted publishing example for DopaMatrix.

This is a reference script, not a production publisher.

It opens an existing BitBrowser profile, connects to the exposed browser through
Chrome DevTools Protocol, navigates to TikTok or Facebook composer pages, uploads
media when a file input can be found, fills text fields best-effort, takes a
screenshot, and then stops for human confirmation.

Usage examples:

    python docs/scripts/publishing/bitbrowser_rpa_example.py ^
      --platform tiktok ^
      --profile-id YOUR_BIT_PROFILE_ID ^
      --media E:\\project\\dopaMatrix\\dopamatrix_delivery_1781700321(1)\\videos\\demo.mp4 ^
      --delivery-csv E:\\project\\dopaMatrix\\dopamatrix_delivery_1781700321(1)\\矩阵投放文案对照表.csv ^
      --screenshot output\\publish-rpa\\tk-demo.png

    python docs/scripts/publishing/bitbrowser_rpa_example.py ^
      --platform facebook ^
      --profile-id YOUR_FB_PROFILE_ID ^
      --media E:\\project\\dopaMatrix\\output\\fb-image.jpg ^
      --caption "Facebook post text" ^
      --screenshot output\\publish-rpa\\fb-demo.png

Requirements:

    pip install requests playwright
    python -m playwright install chromium

BitBrowser must be running locally with Local API enabled. The default API
address used here is http://127.0.0.1:54345.

When a delivery CSV is available, the script can auto-build platform captions
from the CSV row matching the media filename. A minimal account ledger CSV can
also be supplied to resolve profile IDs and defaults.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests


DEFAULT_BIT_API = "http://127.0.0.1:54345"
DEFAULT_TIKTOK_UPLOAD_URL = "https://www.tiktok.com/upload?lang=en"
DEFAULT_FACEBOOK_COMPOSER_URL = "https://business.facebook.com/latest/composer"
DEFAULT_UPLOAD_WAIT_MS = 60_000
DEFAULT_SCREENSHOT = "output/publish-rpa/screenshot.png"
DEFAULT_LOG_JSONL = "output/publish-rpa/publish_logs.jsonl"
DEFAULT_SUMMARY_CSV = "output/publish-rpa/publish_summary.csv"
DEFAULT_PLAN_FILENAME = "publish_plan.csv"
DEFAULT_DELIVERY_CSV_FILENAME = "矩阵投放文案对照表.csv"
DEFAULT_ACCOUNT_LEDGER_FILENAME = "账号环境台账.csv"
FACEBOOK_FILE_CHOOSER_EVENT_WAIT_MS = 8_000
CONTENT_CHECK_ACTIONS = ("pause", "enable", "cancel")
TAB_MODES = ("new", "reuse-first")
FACEBOOK_UPLOAD_MODES = ("auto", "input-only", "file-chooser")
FACEBOOK_CONTENT_MODES = ("post", "reel", "story")
MANUAL_BACKFILL_STATUSES = ("PUBLISHED_MANUAL", "REJECTED_MANUAL", "PREPARED", "FAILED")
SUPPORTED_PLATFORMS = ("tiktok", "facebook")
PLATFORM_CODES = {
    "tiktok": "TK",
    "facebook": "FB",
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PUBLISH_PLAN_FIELDS = [
    "publish_id",
    "client_id",
    "product_id",
    "platform",
    "content_type",
    "facebook_content_mode",
    "composer_url",
    "account_key",
    "browser_profile_id",
    "media_path",
    "title",
    "caption",
    "hashtags",
    "tracking_url",
    "attribution_token",
    "scheduled_at",
    "status",
    "operator",
    "note",
    "last_result_status",
    "last_result_at",
    "result_screenshot",
    "error_type",
    "error_message",
    "post_url",
    "published_at",
    "manual_operator",
    "manual_checked_at",
    "manual_note",
]
SUMMARY_FIELDS = [
    "publish_id",
    "client_id",
    "product_id",
    "platform",
    "content_type",
    "facebook_content_mode",
    "composer_url",
    "account_key",
    "profile_id",
    "profile_name",
    "media_path",
    "title",
    "caption_source",
    "tracking_url",
    "attribution_token",
    "scheduled_at",
    "status",
    "uploaded",
    "caption_filled",
    "media_processing_required",
    "media_processing_confirmed",
    "media_processing_signal",
    "processing_wait_seconds",
    "post_url",
    "published_at",
    "manual_operator",
    "manual_checked_at",
    "manual_note",
    "screenshot",
    "error_type",
    "error_message",
    "duration_seconds",
    "started_at",
    "finished_at",
    "plan_csv",
    "url",
    "checkpoint",
]
SUMMARY_LATEST_OUTCOME_FIELDS = {
    "status",
    "post_url",
    "published_at",
    "manual_operator",
    "manual_checked_at",
    "manual_note",
    "error_type",
    "error_message",
    "finished_at",
}
SUMMARY_PLAN_COLUMNS = {
    "publish_id": ("publish_id", "发布ID", "id"),
    "client_id": ("client_id", "客户ID"),
    "product_id": ("product_id", "产品ID", "sku"),
    "platform": ("platform", "平台"),
    "content_type": ("content_type", "内容类型"),
    "facebook_content_mode": (
        "facebook_content_mode",
        "fb_content_mode",
        "Facebook内容模式",
        "FB内容模式",
        "内容模式",
    ),
    "composer_url": ("composer_url", "facebook_composer_url", "target_url", "发布入口", "入口URL"),
    "account_key": ("account_key", "账号键", "account_code"),
    "profile_id": ("browser_profile_id", "profile_id", "窗口ID", "browser_id"),
    "media_path": ("media_path", "素材路径", "media", "path"),
    "title": ("title", "标题", "社交平台标题"),
    "tracking_url": ("tracking_url", "tracking_link", "追踪短链接", "url"),
    "attribution_token": ("attribution_token", "归因token"),
    "scheduled_at": ("scheduled_at", "排期时间"),
    "status": ("status", "状态"),
    "post_url": ("post_url", "帖子链接", "发布链接"),
    "published_at": ("published_at", "发布时间"),
    "manual_operator": ("manual_operator", "人工操作人"),
    "manual_checked_at": ("manual_checked_at", "人工确认时间"),
    "manual_note": ("manual_note", "人工备注"),
    "screenshot": ("result_screenshot", "结果截图"),
    "error_type": ("error_type", "错误类型"),
    "error_message": ("error_message", "错误信息"),
}
PLAN_STATUS_COLUMNS = {
    "publish_id": ("发布ID", "id"),
    "status": ("状态",),
    "last_result_status": ("最后结果状态",),
    "last_result_at": ("最后结果时间",),
    "result_screenshot": ("结果截图",),
    "error_type": ("错误类型",),
    "error_message": ("错误信息",),
    "post_url": ("帖子链接", "发布链接"),
    "published_at": ("发布时间",),
    "manual_operator": ("人工操作人",),
    "manual_checked_at": ("人工确认时间",),
    "manual_note": ("人工备注",),
}


class BitBrowserError(RuntimeError):
    pass


class NoReadyPublishPlanError(BitBrowserError):
    def __init__(self, candidates: list[Path]) -> None:
        self.candidates = candidates
        searched = "\n".join(f"  - {path}" for path in candidates) or "  (none)"
        super().__init__(
            "One-click mode could not find a publish_plan.csv with READY rows.\n"
            f"Searched:\n{searched}"
        )


@dataclass
class DeliveryPackageCandidate:
    delivery_dir: Path
    delivery_csv: Path
    account_ledger: Path
    plan_path: Path
    media_count: int


def project_root() -> Path:
    script_path = Path(__file__).resolve()
    try:
        return script_path.parents[3]
    except IndexError:
        return Path.cwd().resolve()


def discovery_roots() -> list[Path]:
    roots: list[Path] = []
    for root in (Path.cwd().resolve(), project_root()):
        if root not in roots:
            roots.append(root)
    return roots


def path_has_ignored_parts(path: Path) -> bool:
    ignored_parts = {".git", "node_modules", "__pycache__"}
    return bool(ignored_parts.intersection(path.parts))


def find_publish_plan_candidates() -> list[Path]:
    candidates: list[Path] = []
    for root in discovery_roots():
        if root.is_file() and root.name == DEFAULT_PLAN_FILENAME:
            candidates.append(root)
            continue
        if not root.is_dir():
            continue
        for path in root.rglob(DEFAULT_PLAN_FILENAME):
            if path_has_ignored_parts(path):
                continue
            if path.is_file():
                resolved = path.resolve()
                if resolved not in candidates:
                    candidates.append(resolved)
    return candidates


def ready_publish_plan_candidates(candidates: list[Path]) -> list[tuple[Path, int]]:
    ready_candidates: list[tuple[Path, int]] = []
    for candidate in candidates:
        try:
            ready_count = sum(1 for entry in load_publish_plan(candidate) if entry.is_ready())
        except (OSError, BitBrowserError, UnicodeError):
            continue
        if ready_count:
            ready_candidates.append((candidate, ready_count))
    return ready_candidates


def discover_publish_plan() -> Path:
    candidates = find_publish_plan_candidates()
    ready_candidates = ready_publish_plan_candidates(candidates)
    if len(ready_candidates) == 1:
        return ready_candidates[0][0]
    if not ready_candidates:
        raise NoReadyPublishPlanError(candidates)

    details = "\n".join(
        f"  - {path} ({ready_count} READY rows)"
        for path, ready_count in ready_candidates
    )
    raise SystemExit(
        "One-click mode found multiple publish_plan.csv files with READY rows. "
        "Keep one active plan in the project or pass --plan-csv explicitly.\n"
        f"Candidates:\n{details}"
    )


def find_one_click_generation_candidates() -> list[DeliveryPackageCandidate]:
    candidates: list[DeliveryPackageCandidate] = []
    for root in discovery_roots():
        if not root.is_dir():
            continue
        for delivery_csv in root.rglob(DEFAULT_DELIVERY_CSV_FILENAME):
            if path_has_ignored_parts(delivery_csv) or not delivery_csv.is_file():
                continue
            delivery_dir = delivery_csv.parent.resolve()
            account_ledger = delivery_dir / DEFAULT_ACCOUNT_LEDGER_FILENAME
            plan_path = delivery_dir / DEFAULT_PLAN_FILENAME
            if not account_ledger.is_file() or plan_path.exists():
                continue
            media_count = len(scan_media_files(delivery_dir, VIDEO_EXTENSIONS | IMAGE_EXTENSIONS))
            if media_count == 0:
                continue
            candidate = DeliveryPackageCandidate(
                delivery_dir=delivery_dir,
                delivery_csv=delivery_csv.resolve(),
                account_ledger=account_ledger.resolve(),
                plan_path=plan_path.resolve(),
                media_count=media_count,
            )
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def generate_one_click_publish_plan(
    args: argparse.Namespace,
    existing_plan_candidates: list[Path],
) -> Path:
    candidates = find_one_click_generation_candidates()
    if len(candidates) == 1:
        candidate = candidates[0]
        generation_args = argparse.Namespace(**vars(args))
        generation_args.delivery_dir = str(candidate.delivery_dir)
        generation_args.delivery_csv = str(candidate.delivery_csv)
        generation_args.account_ledger = str(candidate.account_ledger)
        generation_args.output_plan_csv = str(candidate.plan_path)
        generation_args.overwrite_plan = False
        generate_publish_plan(generation_args)
        print(f"One-click generated plan from delivery package: {candidate.delivery_dir}")
        return candidate.plan_path

    searched = "\n".join(f"  - {path}" for path in existing_plan_candidates) or "  (none)"
    if not candidates:
        raise BitBrowserError(
            "One-click mode could not find READY tasks, and no safe delivery package "
            "was available for automatic plan generation.\n"
            f"Existing publish_plan.csv files:\n{searched}\n"
            "If a publish_plan.csv already exists, mark the rows that should run as READY, "
            "or regenerate it explicitly with --generate-plan --overwrite-plan."
        )

    details = "\n".join(
        f"  - {candidate.delivery_dir} ({candidate.media_count} media files)"
        for candidate in candidates
    )
    raise BitBrowserError(
        "One-click mode found multiple delivery packages that could generate publish_plan.csv. "
        "Pass --delivery-dir with --generate-plan first, or leave only one active delivery package.\n"
        f"Candidates:\n{details}"
    )


def configure_one_click(args: argparse.Namespace) -> argparse.Namespace:
    if args.plan_csv:
        plan_path = Path(args.plan_csv).expanduser().resolve()
    else:
        try:
            plan_path = discover_publish_plan()
        except NoReadyPublishPlanError as exc:
            plan_path = generate_one_click_publish_plan(args, exc.candidates)

    args.plan_csv = str(plan_path)
    args.generate_plan = False
    args.include_status = "READY"
    args.continue_on_error = True
    args.write_plan_status = True
    args.tab_mode = "new"
    args.facebook_upload_mode = "auto"
    args.close_task_tab = False
    args.trace_tabs = False
    args.stop_after_connect = False
    args.clean_blank_tabs = False
    if not args.log_jsonl:
        args.log_jsonl = str(project_root() / DEFAULT_LOG_JSONL)

    print("One-click prepare mode")
    print(f"Plan: {plan_path}")
    print("Safety: final Publish/Post buttons will not be clicked.")
    return args


@dataclass
class OpenedProfile:
    profile_id: str
    cdp_url: str
    cdp_source: str
    raw: dict[str, Any]


@dataclass
class DeliveryRecord:
    video_filename: str
    social_title: str = ""
    emotional_description: str = ""
    hashtags: str = ""
    tracking_link: str = ""
    source_csv: str = ""
    raw: dict[str, str] | None = None

    def build_caption(self, platform: str) -> str:
        title = self.social_title or Path(self.video_filename).stem
        description = self.emotional_description.strip()
        hashtags = self.hashtags.strip()

        if platform == "tiktok":
            description = remove_tracking_link(description, self.tracking_link)
        elif platform == "facebook" and self.tracking_link:
            if self.tracking_link not in description:
                description = add_tracking_link(description, self.tracking_link)

        parts = [title, description, hashtags]
        return "\n\n".join(part for part in parts if part)


@dataclass
class AccountLedgerEntry:
    account_key: str
    platform: str = ""
    profile_id: str = ""
    profile_name: str = ""
    content_check_action: str = ""
    notes: str = ""
    raw: dict[str, str] | None = None


@dataclass
class PublishPlanEntry:
    publish_id: str
    platform: str
    client_id: str = ""
    product_id: str = ""
    content_type: str = ""
    facebook_content_mode: str = ""
    composer_url: str = ""
    account_key: str = ""
    browser_profile_id: str = ""
    media_path: str = ""
    title: str = ""
    caption: str = ""
    hashtags: str = ""
    tracking_url: str = ""
    attribution_token: str = ""
    scheduled_at: str = ""
    status: str = ""
    operator: str = ""
    note: str = ""
    raw: dict[str, str] | None = None

    def build_caption(self) -> str:
        description = self.caption.strip()
        tracking_url = self.tracking_url.strip()

        if self.platform == "tiktok":
            description = remove_tracking_link(description, tracking_url)
        elif self.platform == "facebook" and tracking_url:
            description = add_tracking_link(description, tracking_url)

        parts = [self.title.strip(), description, self.hashtags.strip()]
        return "\n\n".join(part for part in parts if part)

    def is_ready(self) -> bool:
        return not self.status or self.status.strip().upper() == "READY"


class BitBrowserClient:
    def __init__(self, base_url: str = DEFAULT_BIT_API, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        response = requests.post(f"{self.base_url}/health", json={}, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def open_profile(self, profile_id: str) -> OpenedProfile:
        payload = {"id": profile_id}
        response = requests.post(
            f"{self.base_url}/browser/open",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()

        if body.get("success") is False:
            raise BitBrowserError(
                "BitBrowser failed to open the profile. "
                f"Raw response: {json.dumps(body, ensure_ascii=False)}"
            )

        data = body.get("data") or {}
        cdp = None
        cdp_source = ""
        for key in ("ws", "http", "debuggingAddress"):
            if data.get(key):
                cdp = data[key]
                cdp_source = key
                break
        if not cdp:
            raise BitBrowserError(
                "BitBrowser opened the profile but did not return a CDP address. "
                f"Raw response: {json.dumps(body, ensure_ascii=False)}"
            )

        return OpenedProfile(
            profile_id=profile_id,
            cdp_url=normalize_cdp_url(cdp, cdp_source),
            cdp_source=cdp_source,
            raw=body,
        )

    def close_profile(self, profile_id: str) -> None:
        requests.post(
            f"{self.base_url}/browser/close",
            json={"id": profile_id},
            timeout=self.timeout,
        )


def normalize_cdp_url(value: str, source: str = "") -> str:
    if value.startswith("ws://") or value.startswith("wss://"):
        return value
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if source == "ws":
        return f"ws://{value}"
    return f"http://{value}"


def _first_nonempty(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _truthy(text: str) -> bool:
    if text is None:
        return False
    return text.strip().lower() in {"1", "true", "yes", "y", "default", "是", "允许"}


def _dedupe_blank_lines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_tracking_link(text: str, tracking_link: str) -> str:
    if not text:
        return ""
    if not tracking_link:
        return _dedupe_blank_lines(text)
    cleaned = text.replace(tracking_link, "")
    return _dedupe_blank_lines(cleaned)


def add_tracking_link(text: str, tracking_link: str) -> str:
    if not text:
        return tracking_link
    if tracking_link in text:
        return text
    cleaned = text.rstrip()
    separator = "\n\n" if cleaned else ""
    return f"{cleaned}{separator}{tracking_link}"


def write_json_log(log_path: Path, payload: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_jsonl_log(log_path: Path, payload: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        fh.write("\n")


def sanitize_tab_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except Exception:
        return url[:180]
    if not parts.scheme or not parts.netloc:
        return url[:180]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:180]


def snapshot_tabs(context: Any, selected_page: Any | None = None) -> list[dict[str, Any]]:
    tabs: list[dict[str, Any]] = []
    for index, tab in enumerate(context.pages, start=1):
        try:
            url = sanitize_tab_url(tab.url)
        except Exception as exc:
            url = f"<url-error:{type(exc).__name__}>"
        tabs.append(
            {
                "index": index,
                "selected": tab == selected_page,
                "url": url,
            }
        )
    return tabs


def read_jsonl_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.is_file():
        raise BitBrowserError(f"JSONL log does not exist: {log_path}")

    records: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                body = json.loads(text)
            except json.JSONDecodeError as exc:
                raise BitBrowserError(
                    f"Invalid JSONL line {line_number} in {log_path}: {exc}"
                ) from exc
            if isinstance(body, dict):
                records.append(body)
    return records


def _summary_value(payload: dict[str, Any], key: str) -> str:
    plan = payload.get("plan") or {}
    result = payload.get("result") or {}
    if key == "started_at":
        value = plan.get("started_at", "")
    elif key in {"finished_at", "url", "checkpoint", "uploaded", "caption_filled"}:
        value = result.get(key, "")
    else:
        value = result.get(key, "")
        if value in (None, ""):
            value = plan.get(key, "")

    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def flatten_publish_log(payload: dict[str, Any]) -> dict[str, str]:
    row = {field: _summary_value(payload, field) for field in SUMMARY_FIELDS}
    if not row["publish_id"]:
        row["publish_id"] = "(manual-entry)"
    return row


def load_plan_summary_index(plan_csv: Path) -> dict[str, dict[str, str]]:
    rows = _read_csv_rows(plan_csv)
    index: dict[str, dict[str, str]] = {}
    for raw_row in rows:
        publish_id = _first_nonempty(raw_row, *SUMMARY_PLAN_COLUMNS["publish_id"])
        if not publish_id:
            continue
        summary: dict[str, str] = {}
        for field, candidate_columns in SUMMARY_PLAN_COLUMNS.items():
            summary[field] = _first_nonempty(raw_row, *candidate_columns)
        index[publish_id] = summary
    return index


def enrich_summary_rows_from_plan(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    plan_cache: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        plan_csv = row.get("plan_csv", "").strip()
        publish_id = row.get("publish_id", "").strip()
        if not plan_csv or not publish_id or publish_id == "(manual-entry)":
            continue
        plan_path = Path(plan_csv).expanduser()
        if not plan_path.is_absolute():
            plan_path = plan_path.resolve()
        plan_key = str(plan_path)
        if plan_key not in plan_cache:
            try:
                plan_cache[plan_key] = load_plan_summary_index(plan_path)
            except Exception:
                plan_cache[plan_key] = {}
        plan_row = plan_cache[plan_key].get(publish_id)
        if not plan_row:
            continue
        for field in SUMMARY_FIELDS:
            if not row.get(field) and plan_row.get(field):
                row[field] = plan_row[field]
    return rows


def _row_sort_time(row: dict[str, str]) -> str:
    return row.get("finished_at") or row.get("started_at") or ""


def merge_summary_row(current: dict[str, str], incoming: dict[str, str]) -> dict[str, str]:
    current_time = _row_sort_time(current)
    incoming_time = _row_sort_time(incoming)
    incoming_is_newer = incoming_time >= current_time
    merged = current.copy()

    if incoming_is_newer:
        for field in SUMMARY_FIELDS:
            value = incoming.get(field, "")
            if field in SUMMARY_LATEST_OUTCOME_FIELDS:
                merged[field] = value
            elif value:
                merged[field] = value
    else:
        for field in SUMMARY_FIELDS:
            if not merged.get(field) and incoming.get(field):
                merged[field] = incoming[field]

    return merged


def write_summary_csv(
    jsonl_path: Path,
    output_csv: Path,
    include_history: bool = False,
) -> list[dict[str, str]]:
    rows = [flatten_publish_log(record) for record in read_jsonl_log(jsonl_path)]
    rows = [row for row in rows if row.get("publish_id")]
    rows = enrich_summary_rows_from_plan(rows)

    if not include_history:
        latest: dict[str, dict[str, str]] = {}
        for row in rows:
            key = row["publish_id"]
            current = latest.get(key)
            if current is None:
                latest[key] = row
            else:
                latest[key] = merge_summary_row(current, row)
        rows = sorted(latest.values(), key=lambda row: (row.get("platform", ""), row.get("publish_id", "")))
    else:
        rows = sorted(rows, key=lambda row: (_row_sort_time(row), row.get("publish_id", "")))

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _resolve_csv_column(fieldnames: list[str], canonical: str) -> str:
    normalized = {field.strip().lower(): field for field in fieldnames if field}
    for candidate in (canonical, *PLAN_STATUS_COLUMNS.get(canonical, ())):
        matched = normalized.get(candidate.strip().lower())
        if matched:
            return matched
    return canonical


def update_publish_plan_row(
    csv_path: Path,
    publish_id: str,
    updates: dict[str, str],
) -> dict[str, str]:
    rows = _read_csv_rows(csv_path)
    if not rows:
        raise BitBrowserError(f"Publish plan is empty: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])

    publish_id_column = _resolve_csv_column(fieldnames, "publish_id")
    if publish_id_column not in fieldnames:
        raise BitBrowserError(f"Publish plan has no publish_id column: {csv_path}")

    column_map: dict[str, str] = {}
    for key in updates:
        column = _resolve_csv_column(fieldnames, key)
        column_map[key] = column
        if column not in fieldnames:
            fieldnames.append(column)

    matched_row: dict[str, str] | None = None
    for row in rows:
        if row.get(publish_id_column, "").strip() != publish_id:
            continue
        for key, value in updates.items():
            row[column_map[key]] = value
        matched_row = row
        break

    if matched_row is None:
        raise BitBrowserError(f"publish_id not found in plan: {publish_id}")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return {column_map[key]: value for key, value in updates.items()}


def build_plan_status_updates(payload: dict[str, Any]) -> dict[str, str]:
    result = payload.get("result") or {}
    finished_at = result.get("finished_at") or datetime.now().isoformat(timespec="seconds")
    status = str(result.get("status") or "FAILED")
    return {
        "status": status,
        "last_result_status": status,
        "last_result_at": str(finished_at),
        "result_screenshot": str(result.get("screenshot") or ""),
        "error_type": str(result.get("error_type") or ""),
        "error_message": str(result.get("error_message") or ""),
    }


def write_plan_status_from_payload(plan_csv: Path, payload: dict[str, Any]) -> dict[str, str]:
    plan = payload.get("plan") or {}
    publish_id = str(plan.get("publish_id") or "").strip()
    if not publish_id:
        raise BitBrowserError("Cannot update publish plan row without publish_id.")
    return update_publish_plan_row(plan_csv, publish_id, build_plan_status_updates(payload))


def write_failure_plan_status_from_payload(
    plan_csv: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    updates = {
        key: value
        for key, value in build_plan_status_updates(payload).items()
        if value or key in {"status", "last_result_status", "last_result_at", "error_type", "error_message"}
    }
    plan = payload.get("plan") or {}
    publish_id = str(plan.get("publish_id") or "").strip()
    if not publish_id:
        raise BitBrowserError("Cannot update publish plan row without publish_id.")
    return update_publish_plan_row(plan_csv, publish_id, updates)


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def load_delivery_records(csv_path: Path) -> list[DeliveryRecord]:
    rows = _read_csv_rows(csv_path)
    if not rows:
        raise BitBrowserError(f"Delivery CSV is empty: {csv_path}")

    records: list[DeliveryRecord] = []
    for row in rows:
        video_filename = _first_nonempty(row, "视频文件名", "video_filename", "media", "media_name")
        records.append(
            DeliveryRecord(
                video_filename=video_filename,
                social_title=_first_nonempty(row, "社交平台标题", "social_title", "title"),
                emotional_description=_first_nonempty(row, "情绪化描述", "social_caption", "caption", "description"),
                hashtags=_first_nonempty(row, "黄金标签", "social_hashtags", "hashtags", "tag"),
                tracking_link=_first_nonempty(row, "追踪短链接", "tracking_link", "url", "link"),
                source_csv=str(csv_path),
                raw=row,
            )
        )
    return records


def _discover_file_upwards(start_dir: Path, candidate_names: tuple[str, ...]) -> Path | None:
    for directory in [start_dir, *start_dir.parents]:
        for candidate_name in candidate_names:
            candidate = directory / candidate_name
            if candidate.is_file():
                return candidate
    return None


def resolve_path_maybe_relative(path_text: str, base_dir: Path) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def load_delivery_record(csv_path: Path, media_path: Path) -> DeliveryRecord:
    records = load_delivery_records(csv_path)

    media_name = media_path.name
    matched = None
    for record in records:
        if record.video_filename == media_name:
            matched = record
            break

    if matched is None:
        if len(records) == 1:
            matched = records[0]
        else:
            available = ", ".join(
                record.video_filename or "<empty>"
                for record in records[:10]
            )
            raise BitBrowserError(
                "No delivery CSV row matched the media filename. "
                f"media={media_name}, csv={csv_path}, sample_rows={available}"
            )

    if not matched.video_filename:
        matched.video_filename = media_name
    return matched


def load_account_ledger(csv_path: Path) -> list[AccountLedgerEntry]:
    rows = _read_csv_rows(csv_path)
    if not rows:
        raise BitBrowserError(f"Account ledger is empty: {csv_path}")

    entries: list[AccountLedgerEntry] = []
    for row in rows:
        entries.append(
            AccountLedgerEntry(
                account_key=_first_nonempty(row, "账号键", "account_key", "account_code", "key"),
                platform=_first_nonempty(row, "平台", "platform"),
                profile_id=_first_nonempty(row, "窗口ID", "profile_id", "browser_profile_id", "browser_id"),
                profile_name=_first_nonempty(row, "窗口名称", "profile_name", "name"),
                content_check_action=_first_nonempty(row, "内容检查处理", "content_check_action", "auto_content_check"),
                notes=_first_nonempty(row, "备注", "notes"),
                raw=row,
            )
        )
    return entries


def load_publish_plan(csv_path: Path) -> list[PublishPlanEntry]:
    rows = _read_csv_rows(csv_path)
    if not rows:
        raise BitBrowserError(f"Publish plan is empty: {csv_path}")

    entries: list[PublishPlanEntry] = []
    for index, row in enumerate(rows, start=1):
        platform = _first_nonempty(row, "platform", "平台").strip().lower()
        media_path = _first_nonempty(row, "media_path", "素材路径", "media", "path")
        publish_id = _first_nonempty(row, "publish_id", "发布ID", "id") or f"PLAN-{index:03d}"
        entries.append(
            PublishPlanEntry(
                publish_id=publish_id,
                platform=platform,
                client_id=_first_nonempty(row, "client_id", "客户ID"),
                product_id=_first_nonempty(row, "product_id", "产品ID", "sku"),
                content_type=_first_nonempty(row, "content_type", "内容类型"),
                facebook_content_mode=_first_nonempty(
                    row,
                    "facebook_content_mode",
                    "fb_content_mode",
                    "Facebook内容模式",
                    "FB内容模式",
                    "内容模式",
                ),
                composer_url=_first_nonempty(
                    row,
                    "composer_url",
                    "facebook_composer_url",
                    "target_url",
                    "发布入口",
                    "入口URL",
                ),
                account_key=_first_nonempty(row, "account_key", "账号键", "account_code"),
                browser_profile_id=_first_nonempty(
                    row,
                    "browser_profile_id",
                    "profile_id",
                    "窗口ID",
                    "browser_id",
                ),
                media_path=media_path,
                title=_first_nonempty(row, "title", "标题", "社交平台标题"),
                caption=_first_nonempty(row, "caption", "文案", "description", "情绪化描述"),
                hashtags=_first_nonempty(row, "hashtags", "标签", "黄金标签"),
                tracking_url=_first_nonempty(row, "tracking_url", "tracking_link", "追踪短链接", "url"),
                attribution_token=_first_nonempty(row, "attribution_token", "归因token"),
                scheduled_at=_first_nonempty(row, "scheduled_at", "排期时间"),
                status=_first_nonempty(row, "status", "状态"),
                operator=_first_nonempty(row, "operator", "操作人"),
                note=_first_nonempty(row, "note", "备注"),
                raw=row,
            )
        )
    return entries


def select_account_entry(
    entries: list[AccountLedgerEntry],
    platform: str,
    profile_id: str | None = None,
    account_key: str | None = None,
) -> AccountLedgerEntry | None:
    platform_key = platform.strip().lower()
    candidates = [
        entry
        for entry in entries
        if not entry.platform or entry.platform.strip().lower() == platform_key
    ]
    if profile_id:
        for entry in candidates or entries:
            if entry.profile_id == profile_id:
                return entry
    if account_key:
        for entry in candidates or entries:
            if entry.account_key == account_key:
                return entry
    if len(candidates) == 1:
        return candidates[0]
    for entry in candidates:
        is_default = ""
        if entry.raw:
            is_default = entry.raw.get("默认") or entry.raw.get("default") or ""
        if _truthy(is_default):
            return entry
    return None


def resolve_delivery_csv(media_path: Path, explicit_csv: str | None) -> Path | None:
    if explicit_csv:
        return Path(explicit_csv).expanduser().resolve()
    return _discover_file_upwards(
        media_path.parent,
        (DEFAULT_DELIVERY_CSV_FILENAME, "delivery.csv", "publish_plan.csv"),
    )


def resolve_account_ledger(media_path: Path, explicit_csv: str | None) -> Path | None:
    if explicit_csv:
        return Path(explicit_csv).expanduser().resolve()
    return _discover_file_upwards(
        media_path.parent,
        (DEFAULT_ACCOUNT_LEDGER_FILENAME, "account-ledger.csv", "account_ledger.csv"),
    )


def resolve_account_ledger_for_task(
    media_path: Path,
    explicit_csv: str | None,
    plan_dir: Path | None = None,
) -> Path | None:
    if explicit_csv:
        return Path(explicit_csv).expanduser().resolve()
    if plan_dir is not None:
        found = _discover_file_upwards(
            plan_dir,
            (DEFAULT_ACCOUNT_LEDGER_FILENAME, "account-ledger.csv", "account_ledger.csv"),
        )
        if found is not None:
            return found
    return resolve_account_ledger(media_path, explicit_csv)


def parse_platform_list(value: str, option_name: str) -> list[str]:
    if not value or value.strip().lower() in {"none", "off", "-"}:
        return []
    platforms: list[str] = []
    for item in value.split(","):
        platform = item.strip().lower()
        if not platform:
            continue
        if platform not in SUPPORTED_PLATFORMS:
            raise BitBrowserError(
                f"Unsupported platform in {option_name}: {platform}. "
                f"Supported: {', '.join(SUPPORTED_PLATFORMS)}"
            )
        if platform not in platforms:
            platforms.append(platform)
    return platforms


def scan_media_files(delivery_dir: Path, extensions: set[str]) -> list[Path]:
    ignored_dirs = {".git", "__pycache__", "node_modules"}
    files: list[Path] = []
    for path in delivery_dir.rglob("*"):
        if not path.is_file():
            continue
        if ignored_dirs.intersection(path.parts):
            continue
        if path.suffix.lower() in extensions:
            files.append(path.resolve())
    return sorted(files, key=lambda item: str(item).lower())


def find_media_by_name(delivery_dir: Path, media_name: str, extensions: set[str]) -> Path | None:
    if not media_name:
        return None
    for path in scan_media_files(delivery_dir, extensions):
        if path.name == media_name:
            return path
    return None


def relative_media_path_for_plan(media_path: Path, base_dir: Path) -> str:
    try:
        return media_path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return str(media_path.resolve())


def short_hash(value: str, length: int = 6) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:length].upper()


def platform_code(platform: str) -> str:
    return PLATFORM_CODES.get(platform, platform[:2].upper())


def make_publish_id(platform: str, media_path: Path, sequence: int) -> str:
    digest = short_hash(f"{platform}|{media_path.resolve()}")
    return f"PUB-{platform_code(platform)}-{datetime.now():%Y%m%d}-{sequence:03d}-{digest}"


def make_attribution_token(
    client_id: str,
    platform: str,
    media_path: Path,
    prefix_override: str = "",
    salt: str = "",
) -> str:
    prefix_source = prefix_override or client_id
    prefix = re.sub(r"[^A-Za-z0-9]+", "", prefix_source).upper() or "AUTO"
    hash_source = str(media_path.resolve()) if not salt else f"{media_path.resolve()}|{salt}"
    return f"{prefix}-{platform_code(platform)}-{short_hash(hash_source)}"


def account_entry_is_usable(entry: AccountLedgerEntry) -> bool:
    if not entry.raw:
        return True
    status = (
        entry.raw.get("状态")
        or entry.raw.get("status")
        or entry.raw.get("账号状态")
        or ""
    ).strip().lower()
    if not status:
        return True
    blocked_words = ("封", "禁用", "停用", "不可用", "失效", "未登录", "blocked", "disabled", "invalid")
    return not any(word in status for word in blocked_words)


def account_entry_sort_key(entry: AccountLedgerEntry) -> tuple[int, str]:
    is_default = ""
    if entry.raw:
        is_default = entry.raw.get("默认") or entry.raw.get("default") or ""
    return (0 if _truthy(is_default) else 1, entry.account_key or entry.profile_id)


def usable_accounts_by_platform(entries: list[AccountLedgerEntry]) -> dict[str, list[AccountLedgerEntry]]:
    result: dict[str, list[AccountLedgerEntry]] = {}
    for platform in SUPPORTED_PLATFORMS:
        accounts = [
            entry
            for entry in entries
            if entry.platform.strip().lower() == platform and account_entry_is_usable(entry)
        ]
        result[platform] = sorted(accounts, key=account_entry_sort_key)
    return result


def choose_round_robin_account(
    accounts_by_platform: dict[str, list[AccountLedgerEntry]],
    counters: dict[str, int],
    platform: str,
) -> AccountLedgerEntry | None:
    accounts = accounts_by_platform.get(platform) or []
    if not accounts:
        return None
    index = counters.get(platform, 0)
    counters[platform] = index + 1
    return accounts[index % len(accounts)]


def scheduled_at_for_row(args: argparse.Namespace, row_index: int) -> str:
    if not args.plan_scheduled_start:
        return ""
    try:
        start = datetime.fromisoformat(args.plan_scheduled_start)
    except ValueError as exc:
        raise BitBrowserError(
            "--plan-scheduled-start must be an ISO time, e.g. 2026-08-14T10:00:00"
        ) from exc
    return (start + timedelta(minutes=args.plan_interval_minutes * (row_index - 1))).isoformat(timespec="minutes")


def resolve_delivery_dir(args: argparse.Namespace) -> Path:
    if args.delivery_dir:
        return Path(args.delivery_dir).expanduser().resolve()
    if args.delivery_csv:
        return Path(args.delivery_csv).expanduser().resolve().parent
    return Path.cwd().resolve()


def resolve_delivery_csv_for_generation(delivery_dir: Path, explicit_csv: str | None) -> Path:
    if explicit_csv:
        path = Path(explicit_csv).expanduser().resolve()
    else:
        path = delivery_dir / DEFAULT_DELIVERY_CSV_FILENAME
    if not path.is_file():
        raise BitBrowserError(f"Delivery CSV not found: {path}")
    return path


def resolve_account_ledger_for_generation(delivery_dir: Path, explicit_csv: str | None) -> Path:
    if explicit_csv:
        path = Path(explicit_csv).expanduser().resolve()
    else:
        path = delivery_dir / DEFAULT_ACCOUNT_LEDGER_FILENAME
    if not path.is_file():
        raise BitBrowserError(f"Account ledger CSV not found: {path}")
    return path


def record_for_media(records: list[DeliveryRecord], media_path: Path) -> DeliveryRecord:
    for record in records:
        if record.video_filename == media_path.name:
            return record
    if len(records) == 1:
        return records[0]
    return DeliveryRecord(video_filename=media_path.name)


def collect_generation_media(
    delivery_dir: Path,
    records: list[DeliveryRecord],
    warnings: list[str],
) -> tuple[list[tuple[Path, DeliveryRecord]], list[tuple[Path, DeliveryRecord]]]:
    videos: list[tuple[Path, DeliveryRecord]] = []
    used_video_paths: set[Path] = set()
    for record in records:
        media_path = find_media_by_name(delivery_dir, record.video_filename, VIDEO_EXTENSIONS)
        if media_path is None:
            if record.video_filename:
                warnings.append(f"Delivery CSV row has no matching video file: {record.video_filename}")
            continue
        videos.append((media_path, record))
        used_video_paths.add(media_path)

    for media_path in scan_media_files(delivery_dir, VIDEO_EXTENSIONS):
        if media_path not in used_video_paths:
            videos.append((media_path, record_for_media(records, media_path)))

    images = [
        (media_path, record_for_media(records, media_path))
        for media_path in scan_media_files(delivery_dir, IMAGE_EXTENSIONS)
    ]
    return videos, images


def build_generated_plan_row(
    args: argparse.Namespace,
    plan_base_dir: Path,
    media_path: Path,
    record: DeliveryRecord,
    platform: str,
    content_type: str,
    row_index: int,
    account: AccountLedgerEntry,
) -> dict[str, str]:
    tracking_url = record.tracking_link
    attribution_token = make_attribution_token(
        args.plan_client_id,
        platform,
        media_path,
        args.plan_attribution_prefix,
        str(row_index) if args.plan_repeat > 1 else "",
    )
    note = args.plan_note or "自动生成；脚本只准备草稿，最终发布由人工确认。"
    facebook_content_mode = ""
    composer_url = ""
    if platform == "facebook":
        facebook_content_mode = "post"
        if content_type == "video":
            facebook_content_mode = args.plan_facebook_video_mode
            composer_url = args.plan_facebook_video_composer_url
    return {
        "publish_id": make_publish_id(platform, media_path, row_index),
        "client_id": args.plan_client_id or "",
        "product_id": args.plan_product_id or "",
        "platform": platform,
        "content_type": content_type,
        "facebook_content_mode": facebook_content_mode,
        "composer_url": composer_url,
        "account_key": account.account_key,
        "browser_profile_id": "",
        "media_path": relative_media_path_for_plan(media_path, plan_base_dir),
        "title": record.social_title,
        "caption": record.emotional_description,
        "hashtags": record.hashtags,
        "tracking_url": tracking_url,
        "attribution_token": attribution_token,
        "scheduled_at": scheduled_at_for_row(args, row_index),
        "status": args.plan_initial_status,
        "operator": args.plan_operator or "",
        "note": note,
        "last_result_status": "",
        "last_result_at": "",
        "result_screenshot": "",
        "error_type": "",
        "error_message": "",
        "post_url": "",
        "published_at": "",
        "manual_operator": "",
        "manual_checked_at": "",
        "manual_note": "",
    }


def write_generated_plan(output_path: Path, rows: list[dict[str, str]], overwrite: bool) -> None:
    if output_path.exists() and not overwrite:
        raise BitBrowserError(
            f"Publish plan already exists: {output_path}. "
            "Pass --overwrite-plan or choose --output-plan-csv."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PUBLISH_PLAN_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def generate_publish_plan(args: argparse.Namespace) -> int:
    delivery_dir = resolve_delivery_dir(args)
    if not delivery_dir.is_dir():
        raise BitBrowserError(f"Delivery directory not found: {delivery_dir}")

    delivery_csv = resolve_delivery_csv_for_generation(delivery_dir, args.delivery_csv)
    account_ledger = resolve_account_ledger_for_generation(delivery_dir, args.account_ledger)
    output_path = (
        Path(args.output_plan_csv).expanduser().resolve()
        if args.output_plan_csv
        else delivery_dir / DEFAULT_PLAN_FILENAME
    )
    video_platforms = parse_platform_list(args.plan_video_platforms, "--plan-video-platforms")
    image_platforms = parse_platform_list(args.plan_image_platforms, "--plan-image-platforms")
    if args.plan_repeat < 1:
        raise BitBrowserError("--plan-repeat must be 1 or greater.")

    records = load_delivery_records(delivery_csv)
    accounts_by_platform = usable_accounts_by_platform(load_account_ledger(account_ledger))
    warnings: list[str] = []
    videos, images = collect_generation_media(delivery_dir, records, warnings)
    if (
        "facebook" in video_platforms
        and args.plan_facebook_video_mode != "post"
        and not args.plan_facebook_video_composer_url
    ):
        warnings.append(
            "Facebook video mode is not post, but --plan-facebook-video-composer-url is empty. "
            "Rows will rely on the runtime default composer URL unless a composer_url is filled manually."
        )
    account_counters: dict[str, int] = {}
    rows: list[dict[str, str]] = []

    def add_rows(
        media_items: list[tuple[Path, DeliveryRecord]],
        platforms: list[str],
        content_type: str,
    ) -> None:
        for media_path, record in media_items:
            for platform in platforms:
                for _ in range(args.plan_repeat):
                    account = choose_round_robin_account(accounts_by_platform, account_counters, platform)
                    if account is None:
                        warnings.append(f"No usable account for {platform}; skipped {media_path.name}")
                        continue
                    rows.append(
                        build_generated_plan_row(
                            args,
                            output_path.parent,
                            media_path,
                            record,
                            platform,
                            content_type,
                            len(rows) + 1,
                            account,
                        )
                    )

    add_rows(videos, video_platforms, "video")
    add_rows(images, image_platforms, "image")

    if not rows:
        detail = "\n".join(f"  - {warning}" for warning in warnings) or "  (no media found)"
        raise BitBrowserError(f"No publish plan rows generated.\n{detail}")

    write_generated_plan(output_path, rows, args.overwrite_plan)
    print(f"Generated publish plan: {output_path}")
    print(f"Rows: {len(rows)}")
    print(f"Delivery CSV: {delivery_csv}")
    print(f"Account ledger: {account_ledger}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    return 0


def connect_browser_context(cdp_url: str):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is not installed. Run: pip install playwright && "
            "python -m playwright install chromium"
        ) from exc

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return pw, browser, context


def connect_page(cdp_url: str, tab_mode: str = "new", trace_tabs: bool = False):
    pw, browser, context = connect_browser_context(cdp_url)
    trace: dict[str, Any] = {"tab_mode": tab_mode}
    if trace_tabs:
        trace["before"] = snapshot_tabs(context)
    if tab_mode == "reuse-first":
        page = context.pages[0] if context.pages else context.new_page()
    elif tab_mode == "new":
        page = context.new_page()
    else:
        raise BitBrowserError(f"Unsupported tab mode: {tab_mode}")
    if trace_tabs:
        trace["after_select"] = snapshot_tabs(context, page)
        print("Tab trace:", json.dumps(trace, ensure_ascii=False, indent=2))
    return pw, browser, page, trace


def close_page_best_effort(page: Any | None) -> None:
    if page is None:
        return
    try:
        page.close()
    except Exception:
        pass


def close_blank_tabs(context: Any, keep_one_blank: bool = False) -> list[dict[str, Any]]:
    closed: list[dict[str, Any]] = []
    blank_pages = [page for page in context.pages if sanitize_tab_url(page.url) == "about:blank"]
    if keep_one_blank and blank_pages:
        blank_pages = blank_pages[1:]
    for page in blank_pages:
        before_close = snapshot_tabs(context, page)
        close_page_best_effort(page)
        closed.append(
            {
                "url": "about:blank",
                "before_close": before_close,
            }
        )
    return closed


def set_first_file_input(page, media_path: Path, timeout_ms: int = DEFAULT_UPLOAD_WAIT_MS) -> bool:
    input_locator = page.locator("input[type='file']").first
    try:
        input_locator.wait_for(state="attached", timeout=timeout_ms)
    except Exception:
        return False
    input_locator.set_input_files(str(media_path))
    return True


def click_upload_entry_best_effort(page) -> bool:
    selectors = [
        "a[href*='/upload']",
        "button:has-text('Upload')",
        "div[role='button']:has-text('Upload')",
        "text=/^Upload$/i",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if locator.count() == 0:
                continue
            locator.first.click(timeout=5000)
            return True
        except Exception:
            continue
    return False


def upload_via_facebook_media_button(page, media_path: Path, timeout_ms: int) -> bool:
    selectors = [
        "[role='button']:has-text('添加照片/视频')",
        "button:has-text('添加照片/视频')",
        "div[role='button']:has-text('添加照片/视频')",
        "span:has-text('添加照片/视频')",
        "[role='button']:has-text('添加照片')",
        "button:has-text('添加照片')",
        "div[role='button']:has-text('添加照片')",
        "span:has-text('添加照片')",
        "[role='button']:has-text('添加视频')",
        "button:has-text('添加视频')",
        "div[role='button']:has-text('添加视频')",
        "span:has-text('添加视频')",
        "[role='button']:has-text('添加媒体')",
        "button:has-text('添加媒体')",
        "div[role='button']:has-text('添加媒体')",
        "span:has-text('添加媒体')",
        "text=/添加照片/",
        "text=/添加视频/",
        "text=/添加媒体/",
        "[aria-label*='添加照片' i]",
        "[aria-label*='添加视频' i]",
        "[aria-label*='添加媒体' i]",
        "[aria-label*='照片' i]",
        "[aria-label*='视频' i]",
        "[aria-label*='媒体' i]",
        "[role='button']:has-text('Add photo/video')",
        "button:has-text('Add photo/video')",
        "div[role='button']:has-text('Add photo/video')",
        "span:has-text('Add photo/video')",
        "[role='button']:has-text('Photo/video')",
        "button:has-text('Photo/video')",
        "div[role='button']:has-text('Photo/video')",
        "span:has-text('Photo/video')",
        "[role='button']:has-text('Add video')",
        "button:has-text('Add video')",
        "div[role='button']:has-text('Add video')",
        "span:has-text('Add video')",
        "[role='button']:has-text('Upload video')",
        "button:has-text('Upload video')",
        "div[role='button']:has-text('Upload video')",
        "span:has-text('Upload video')",
        "[role='button']:has-text('Add media')",
        "button:has-text('Add media')",
        "div[role='button']:has-text('Add media')",
        "span:has-text('Add media')",
        "[role='button']:has-text('Create reel')",
        "button:has-text('Create reel')",
        "div[role='button']:has-text('Create reel')",
        "span:has-text('Create reel')",
        "[aria-label*='Add photo' i]",
        "[aria-label*='Add video' i]",
        "[aria-label*='Upload video' i]",
        "[aria-label*='Add media' i]",
        "[aria-label*='reel' i]",
        "[aria-label*='photo' i]",
        "[aria-label*='video' i]",
        "[aria-label*='media' i]",
        "text=/Add photo\\/video/i",
        "text=/Photo\\/video/i",
        "text=/Add video/i",
        "text=/Upload video/i",
        "text=/Add media/i",
        "text=/Create reel/i",
        "text=/添加照片\\/视频/",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if locator.count() == 0:
                continue
            with page.expect_file_chooser(
                timeout=min(timeout_ms, FACEBOOK_FILE_CHOOSER_EVENT_WAIT_MS)
            ) as chooser_info:
                locator.first.click(timeout=5000)
            chooser_info.value.set_files(str(media_path))
            return True
        except Exception:
            continue
    return False


FACEBOOK_MEDIA_BUSY_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in (
        r"正在上传影音内容",
        r"正在上传",
        r"上传中",
        r"正在处理",
        r"处理中",
        r"uploading\s+(media|video|file)",
        r"(media|video|file)\s+uploading",
        r"processing\s+(media|video|file)",
        r"(media|video|file)\s+processing",
    )
]

FACEBOOK_VIDEO_READY_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in (
        r"\d{2,4}\s*[x×]\s*\d{2,4}\s*[•·]\s*\d{1,2}:\d{2}",
        r"把你的视频作为\s*Reels?\s*发布",
        r"转至\s*Reels?\s*编辑器",
        r"Reels?\s*编辑器",
        r"编辑视频",
        r"视频详情",
        r"视频预览",
        r"video\s+details",
        r"edit\s+video",
        r"video\s+preview",
        r"go\s+to\s+reels?\s+editor",
        r"publish\s+your\s+video\s+as\s+a\s+reel",
    )
]


def first_matching_pattern(patterns: list[re.Pattern[str]], text: str) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(0)[:80]
    return ""


def wait_for_facebook_media_processing(
    page,
    media_path: Path,
    uploaded: bool,
    timeout_ms: int,
) -> dict[str, Any]:
    started = time.monotonic()
    media_suffix = media_path.suffix.lower()
    required = uploaded and media_suffix in VIDEO_EXTENSIONS
    if not uploaded:
        return {
            "media_processing_required": media_suffix in VIDEO_EXTENSIONS,
            "media_processing_confirmed": False,
            "media_processing_signal": "upload_not_confirmed",
            "processing_wait_seconds": 0,
        }
    if not required:
        return {
            "media_processing_required": False,
            "media_processing_confirmed": True,
            "media_processing_signal": "not_required_for_image",
            "processing_wait_seconds": 0,
        }

    last_signal = "waiting_for_video_ready_signal"
    deadline = started + max(timeout_ms, 1_000) / 1000
    while time.monotonic() < deadline:
        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=2_000)
        except Exception as exc:
            last_signal = f"text_read_error:{type(exc).__name__}"

        busy_signal = first_matching_pattern(FACEBOOK_MEDIA_BUSY_PATTERNS, body_text)
        ready_signal = first_matching_pattern(FACEBOOK_VIDEO_READY_PATTERNS, body_text)
        try:
            if not ready_signal and page.locator("video").count() > 0:
                ready_signal = "video_element"
        except Exception:
            pass

        if ready_signal and not busy_signal:
            return {
                "media_processing_required": True,
                "media_processing_confirmed": True,
                "media_processing_signal": ready_signal,
                "processing_wait_seconds": round(time.monotonic() - started, 2),
            }
        if ready_signal and busy_signal:
            last_signal = f"ready:{ready_signal}; busy:{busy_signal}"
        elif busy_signal:
            last_signal = f"busy:{busy_signal}"
        elif body_text:
            last_signal = "no_ready_or_busy_signal"
        page.wait_for_timeout(2_000)

    return {
        "media_processing_required": True,
        "media_processing_confirmed": False,
        "media_processing_signal": last_signal,
        "processing_wait_seconds": round(time.monotonic() - started, 2),
    }


def dismiss_safe_popups(page) -> list[str]:
    clicked: list[str] = []
    selectors = [
        "button:has-text('Got it')",
        "button:has-text('Not now')",
        "button:has-text('Maybe later')",
    ]
    for _ in range(5):
        clicked_in_pass = False
        for selector in selectors:
            locator = page.locator(selector)
            try:
                if locator.count() == 0:
                    continue
                locator.first.click(timeout=3000)
                clicked.append(selector)
                clicked_in_pass = True
                page.wait_for_timeout(1000)
            except Exception:
                continue
        if not clicked_in_pass:
            break
    return clicked


def handle_content_check_popup(page, action: str) -> dict[str, Any]:
    popup = page.get_by_text("Turn on automatic content checks?", exact=True)
    try:
        if popup.count() == 0:
            return {"detected": False, "action": action}
    except Exception:
        return {"detected": False, "action": action}

    if action == "pause":
        raise BitBrowserError(
            "TikTok is asking whether to turn on automatic content checks. "
            "The script is paused by default because this changes an account-level setting. "
            "Manually choose in the browser, or rerun with --content-check-action enable/cancel."
        )

    button_text = "Turn on" if action == "enable" else "Cancel"
    page.get_by_role("button", name=button_text).click(timeout=5000)
    page.wait_for_timeout(1500)
    return {"detected": True, "action": action}


def fill_text_best_effort(page, caption: str, timeout_ms: int = 10_000) -> bool:
    selectors = [
        "textarea",
        "div[aria-label*='Description' i]",
        "[contenteditable='true']",
        "[role='textbox']",
        "[data-e2e*='caption' i]",
        "[data-e2e*='description' i]",
        "div[aria-label*='caption' i]",
        "div[aria-label*='post' i]",
        "div[aria-label*='write' i]",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            locator.first.wait_for(state="attached", timeout=timeout_ms)
            target = locator.first
            target.click(timeout=3000)
            if selector == "textarea":
                target.fill(caption, timeout=3000)
            else:
                page.keyboard.press("Control+A")
                page.keyboard.insert_text(caption)
            return True
        except Exception:
            continue
    return False


def publish_tiktok(
    page,
    media_path: Path,
    caption: str,
    upload_wait_ms: int = DEFAULT_UPLOAD_WAIT_MS,
    content_check_action: str = "pause",
) -> dict[str, Any]:
    page.goto(DEFAULT_TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3000)

    uploaded = set_first_file_input(page, media_path, upload_wait_ms)
    clicked_upload_entry = False
    if not uploaded:
        clicked_upload_entry = click_upload_entry_best_effort(page)
        if clicked_upload_entry:
            page.wait_for_timeout(3000)
            uploaded = set_first_file_input(page, media_path, upload_wait_ms)
    if uploaded:
        page.wait_for_timeout(8000)

    content_check = handle_content_check_popup(page, content_check_action)
    dismissed_popups = dismiss_safe_popups(page)
    caption_filled = fill_text_best_effort(page, caption)
    return {
        "platform": "tiktok",
        "url": page.url,
        "uploaded": uploaded,
        "caption_filled": caption_filled,
        "clicked_upload_entry": clicked_upload_entry,
        "content_check": content_check,
        "dismissed_popups": dismissed_popups,
        "checkpoint": "请人工检查视频、caption、版权/商业内容声明，然后手动点击发布。",
    }


def publish_facebook(
    page,
    media_path: Path,
    caption: str,
    upload_wait_ms: int = DEFAULT_UPLOAD_WAIT_MS,
    upload_mode: str = "auto",
    composer_url: str = DEFAULT_FACEBOOK_COMPOSER_URL,
    content_mode: str = "post",
) -> dict[str, Any]:
    target_url = composer_url or DEFAULT_FACEBOOK_COMPOSER_URL
    page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(5000)

    dismissed_popups = dismiss_safe_popups(page)
    uploaded = False
    direct_input_attempted = upload_mode in {"auto", "input-only"}
    file_chooser_attempted = upload_mode in {"auto", "file-chooser"}
    if direct_input_attempted:
        uploaded = set_first_file_input(page, media_path, min(upload_wait_ms, 10_000))
    used_file_chooser = False
    if not uploaded and file_chooser_attempted:
        uploaded = upload_via_facebook_media_button(page, media_path, upload_wait_ms)
        used_file_chooser = uploaded
    if uploaded:
        page.wait_for_timeout(5000)
    media_processing = wait_for_facebook_media_processing(
        page,
        media_path,
        uploaded,
        upload_wait_ms,
    )
    caption_filled = fill_text_best_effort(page, caption)

    return {
        "platform": "facebook",
        "url": page.url,
        "uploaded": uploaded,
        "caption_filled": caption_filled,
        "composer_url": target_url,
        "content_mode": content_mode,
        "upload_mode": upload_mode,
        "direct_input_attempted": direct_input_attempted,
        "file_chooser_attempted": file_chooser_attempted,
        "used_file_chooser": used_file_chooser,
        **media_processing,
        "dismissed_popups": dismissed_popups,
        "checkpoint": facebook_checkpoint(content_mode),
    }


def facebook_checkpoint(content_mode: str) -> str:
    if content_mode == "reel":
        return "请人工检查 Page/Reels 入口是否正确、视频预览、caption、音乐/版权和发布设置，然后手动点击发布。"
    if content_mode == "story":
        return "请人工检查 Page/快拍入口是否正确、素材预览、贴纸/链接和发布设置，然后手动点击发布。"
    return "请人工检查 Page 是否正确、图片/视频/文案预览、发布或排期设置，然后手动点击发布。"


class PlatformPublisher:
    platform = ""

    def prepare(
        self,
        page: Any,
        media_path: Path,
        caption: str,
        args: argparse.Namespace,
        content_check_action: str,
    ) -> dict[str, Any]:
        raise NotImplementedError


class TikTokPublisher(PlatformPublisher):
    platform = "tiktok"

    def prepare(
        self,
        page: Any,
        media_path: Path,
        caption: str,
        args: argparse.Namespace,
        content_check_action: str,
    ) -> dict[str, Any]:
        return publish_tiktok(
            page,
            media_path,
            caption,
            args.upload_wait_ms,
            content_check_action,
        )


class FacebookPublisher(PlatformPublisher):
    platform = "facebook"

    def prepare(
        self,
        page: Any,
        media_path: Path,
        caption: str,
        args: argparse.Namespace,
        content_check_action: str,
    ) -> dict[str, Any]:
        return publish_facebook(
            page,
            media_path,
            caption,
            args.upload_wait_ms,
            args.facebook_upload_mode,
            args.facebook_composer_url,
            args.facebook_content_mode,
        )


PUBLISHERS: dict[str, PlatformPublisher] = {
    publisher.platform: publisher
    for publisher in (
        TikTokPublisher(),
        FacebookPublisher(),
    )
}


def get_publisher(platform: str) -> PlatformPublisher:
    publisher = PUBLISHERS.get(platform)
    if publisher is None:
        raise SystemExit(f"Unsupported platform: {platform}")
    return publisher


def default_screenshot_path(platform: str, publish_id: str = "") -> Path:
    if publish_id:
        safe_publish_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", publish_id).strip("_")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return Path("output") / "publish-rpa" / f"{safe_publish_id}-{platform}-{timestamp}.png"
    return Path(DEFAULT_SCREENSHOT)


def classify_error(error_type: str, error_message: str, platform: str = "") -> str:
    haystack = f"{error_type} {error_message}".lower()
    platform_key = platform.lower()
    if "unsupported platform" in haystack:
        return "UNSUPPORTED_PLATFORM"
    if "media file does not exist" in haystack or "empty_media_path" in haystack:
        return "MEDIA_PATH_INVALID"
    if (
        "unsupported file" in haystack
        or "unsupported format" in haystack
        or "file type" in haystack
        or "video format" in haystack
    ):
        return "MEDIA_FORMAT_UNSUPPORTED"
    if "profile-id is required" in haystack or "publish_id not found" in haystack:
        return "PLAN_CONFIG_INVALID"
    if "playwright is not installed" in haystack:
        return "LOCAL_DEPENDENCY_MISSING"
    if (
        "err_proxy_connection_failed" in haystack
        or "err_tunnel_connection_failed" in haystack
        or "proxy_connection_failed" in haystack
    ):
        return "PROXY_CONNECTION_FAILED"
    if "failed to establish a new connection" in haystack or "/health" in haystack:
        return "BITBROWSER_CONNECTION"
    if "connect_over_cdp" in haystack or "websocket error" in haystack or "econnrefused" in haystack:
        return "BITBROWSER_CONNECTION"
    if "failed to open the profile" in haystack or "did not return a cdp address" in haystack:
        return "BITBROWSER_PROFILE_OPEN"
    if "target page" in haystack and "closed" in haystack:
        return "BROWSER_TARGET_CLOSED"
    if "too many requests" in haystack or "rate limit" in haystack or "temporarily blocked" in haystack:
        return "PLATFORM_RATE_LIMIT_OR_RESTRICTION"
    if platform_key == "facebook" and "file chooser" in haystack and "timeout" in haystack:
        return "FACEBOOK_FILE_CHOOSER_TIMEOUT"
    if platform_key == "facebook" and "page" in haystack and (
        "permission" in haystack
        or "access" in haystack
        or "not found" in haystack
        or "unavailable" in haystack
    ):
        return "FACEBOOK_PAGE_ACCESS"
    if "content checks" in haystack:
        return "TIKTOK_CONTENT_CHECK_SETTING" if platform_key == "tiktok" else "ACCOUNT_SETTING_CHECK"
    if (
        "verification" in haystack
        or "captcha" in haystack
        or "identity" in haystack
        or "人脸" in haystack
        or re.search(r"\bface\s+(verification|check|scan|id)\b", haystack)
    ):
        return "ACCOUNT_VERIFICATION"
    if "login" in haystack or "log in" in haystack or "sign in" in haystack:
        return "LOGIN_REQUIRED"
    if "timeout" in haystack:
        return "PLATFORM_TIMEOUT"
    return error_type or "UNKNOWN_ERROR"


def classify_partial_result(result: dict[str, Any]) -> tuple[str, str]:
    platform = str(result.get("platform", "")).lower()
    if not result.get("uploaded"):
        if platform == "tiktok":
            return "TIKTOK_UPLOAD_NOT_CONFIRMED", "TikTok media upload was not confirmed by the page."
        if platform == "facebook":
            return "FACEBOOK_UPLOAD_NOT_CONFIRMED", "Facebook media upload was not confirmed by the page."
        return "UPLOAD_NOT_CONFIRMED", "Media upload was not confirmed by the page."
    if (
        platform == "facebook"
        and result.get("media_processing_required")
        and not result.get("media_processing_confirmed")
    ):
        return (
            "FACEBOOK_MEDIA_PROCESSING_NOT_CONFIRMED",
            "Facebook video upload finished selecting the file, but the page did not confirm media processing before timeout.",
        )
    if not result.get("caption_filled"):
        if platform == "tiktok":
            return "TIKTOK_CAPTION_NOT_FILLED", "TikTok caption field was not filled."
        if platform == "facebook":
            return "FACEBOOK_CAPTION_NOT_FILLED", "Facebook post text field was not filled."
        return "CAPTION_NOT_FILLED", "Caption field was not filled."
    return "", ""


def duration_seconds_since(started_at: str) -> float | None:
    if not started_at:
        return None
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return None
    return round((datetime.now() - started).total_seconds(), 2)


def append_plan_failure(
    args: argparse.Namespace,
    plan_path: Path,
    entry: PublishPlanEntry,
    error_type: str,
    error_message: str,
    task_started_at: str | None = None,
    media_path: str = "",
) -> None:
    started_at = task_started_at or datetime.now().isoformat(timespec="seconds")
    payload = {
        "plan": {
            "started_at": started_at,
            "publish_id": entry.publish_id,
            "client_id": entry.client_id,
            "product_id": entry.product_id,
            "platform": entry.platform,
            "content_type": entry.content_type,
            "account_key": entry.account_key,
            "profile_id": entry.browser_profile_id,
            "media_path": media_path or entry.media_path,
            "plan_csv": str(plan_path),
            "plan_row_status": entry.status,
            "caption_source": "plan_csv",
        },
        "result": {
            "status": "FAILED",
            "error_type": classify_error(error_type, error_message, entry.platform),
            "error_message": error_message,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "duration_seconds": duration_seconds_since(started_at),
        },
    }
    if args.log_jsonl:
        append_jsonl_log(Path(args.log_jsonl).expanduser().resolve(), payload)
    if getattr(args, "write_plan_status", False):
        write_failure_plan_status_from_payload(plan_path, payload)


def write_failure_logs(
    args: argparse.Namespace,
    plan: dict[str, Any],
    error_type: str,
    error_message: str,
    page: Any | None = None,
    screenshot_path: Path | None = None,
) -> dict[str, Any]:
    result = {
        "status": "FAILED",
        "error_type": classify_error(error_type, error_message, str(plan.get("platform", ""))),
        "raw_error_type": error_type,
        "error_message": error_message,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "duration_seconds": duration_seconds_since(str(plan.get("started_at", ""))),
    }
    if page is not None and screenshot_path is not None:
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
            result["screenshot"] = str(screenshot_path)
        except Exception as screenshot_exc:
            result["screenshot_error"] = str(screenshot_exc)
    payload = {"plan": plan, "result": result}
    if args.log_json:
        write_json_log(Path(args.log_json).expanduser().resolve(), payload)
    if args.log_jsonl:
        append_jsonl_log(Path(args.log_jsonl).expanduser().resolve(), payload)
    return payload


def run_single(args: argparse.Namespace) -> dict[str, Any]:
    media_path = Path(args.media).expanduser().resolve()
    if not media_path.exists():
        raise SystemExit(f"Media file does not exist: {media_path}")

    screenshot_arg = args.screenshot or str(default_screenshot_path(args.platform, args.publish_id))
    screenshot_path = Path(screenshot_arg).expanduser().resolve()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    delivery_csv = resolve_delivery_csv(media_path, args.delivery_csv)
    delivery_record: DeliveryRecord | None = None
    if delivery_csv is not None:
        delivery_record = load_delivery_record(delivery_csv, media_path)
        print(
            "Delivery record:",
            json.dumps(
                {
                    "source_csv": delivery_record.source_csv,
                    "video_filename": delivery_record.video_filename,
                    "social_title": delivery_record.social_title,
                    "tracking_link": delivery_record.tracking_link,
                },
                ensure_ascii=False,
            ),
        )

    account_ledger_path = resolve_account_ledger_for_task(
        media_path,
        args.account_ledger,
        getattr(args, "plan_dir", None),
    )
    account_entry: AccountLedgerEntry | None = None
    if account_ledger_path is not None:
        account_entries = load_account_ledger(account_ledger_path)
        account_entry = select_account_entry(
            account_entries,
            args.platform,
            profile_id=args.profile_id,
            account_key=args.account_key,
        )
        if account_entry is not None:
            print(
                "Account ledger entry:",
                json.dumps(
                    {
                        "source_csv": str(account_ledger_path),
                        "account_key": account_entry.account_key,
                        "platform": account_entry.platform,
                        "profile_id": account_entry.profile_id,
                        "profile_name": account_entry.profile_name,
                        "content_check_action": account_entry.content_check_action,
                    },
                    ensure_ascii=False,
                ),
            )

    profile_id = args.profile_id or (account_entry.profile_id if account_entry else None)
    if not profile_id:
        raise SystemExit(
            "profile-id is required unless it can be loaded from an account ledger."
        )

    content_check_action = args.content_check_action
    if content_check_action is None and account_entry and account_entry.content_check_action:
        content_check_action = account_entry.content_check_action
    if content_check_action is None:
        content_check_action = "pause"

    caption = args.caption
    caption_source = ""
    if not caption and delivery_record is not None:
        caption = delivery_record.build_caption(args.platform)
        caption_source = "delivery_csv"
        print("Caption source: delivery CSV")
    elif caption:
        caption_source = "plan_csv" if getattr(args, "from_plan", False) else "manual_arg"
        print(f"Caption source: {caption_source}")
    else:
        raise SystemExit(
            "caption is required unless a delivery CSV is available and matches the media filename."
        )

    run_started_at = datetime.now().isoformat(timespec="seconds")
    facebook_content_mode = args.facebook_content_mode if args.platform == "facebook" else ""
    facebook_composer_url = args.facebook_composer_url if args.platform == "facebook" else ""
    plan = {
        "started_at": run_started_at,
        "publish_id": args.publish_id,
        "client_id": getattr(args, "client_id", ""),
        "product_id": getattr(args, "product_id", ""),
        "platform": args.platform,
        "content_type": args.content_type,
        "profile_id": profile_id,
        "account_key": account_entry.account_key if account_entry else args.account_key,
        "account_platform": account_entry.platform if account_entry else "",
        "profile_name": account_entry.profile_name if account_entry else "",
        "media_path": str(media_path),
        "delivery_csv": str(delivery_csv) if delivery_csv else "",
        "account_ledger": str(account_ledger_path) if account_ledger_path else "",
        "title": getattr(args, "title", ""),
        "caption_source": caption_source,
        "caption": caption,
        "tracking_url": getattr(args, "tracking_url", ""),
        "attribution_token": getattr(args, "attribution_token", ""),
        "scheduled_at": getattr(args, "scheduled_at", ""),
        "facebook_content_mode": facebook_content_mode,
        "composer_url": facebook_composer_url,
        "content_check_action": content_check_action,
        "tab_mode": getattr(args, "tab_mode", "new"),
        "screenshot": str(screenshot_path),
    }
    if getattr(args, "plan_csv_path", None):
        plan["plan_csv"] = str(args.plan_csv_path)
        plan["plan_row_status"] = getattr(args, "plan_row_status", "")
    if args.print_plan:
        print(json.dumps({"plan": plan}, ensure_ascii=False, indent=2))
        return {"plan": plan, "result": {"status": "PLANNED"}}

    bit = BitBrowserClient(args.bit_api)
    health = bit.health()
    print("BitBrowser health:", json.dumps(health, ensure_ascii=False))

    opened = bit.open_profile(profile_id)
    print("Opened profile:", opened.profile_id)
    print(f"CDP URL ({opened.cdp_source}):", opened.cdp_url)

    pw = None
    browser = None
    page = None
    tab_trace: dict[str, Any] = {}
    try:
        pw, browser, page, tab_trace = connect_page(
            opened.cdp_url,
            args.tab_mode,
            args.trace_tabs,
        )
        if args.stop_after_connect:
            result = {
                "status": "CONNECTED",
                "tab_mode": args.tab_mode,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "duration_seconds": duration_seconds_since(run_started_at),
            }
            if args.trace_tabs and browser is not None:
                result["tab_trace_after_connect"] = snapshot_tabs(
                    browser.contexts[0],
                    page,
                )
                print(
                    "Tab trace after connect:",
                    json.dumps(result["tab_trace_after_connect"], ensure_ascii=False, indent=2),
                )
            log_payload = {
                "plan": plan,
                "bitbrowser": {
                    "health": health,
                    "opened_profile": {
                        "profile_id": opened.profile_id,
                        "cdp_source": opened.cdp_source,
                    },
                    "tab_trace": tab_trace,
                },
                "result": result,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if args.log_json:
                write_json_log(Path(args.log_json).expanduser().resolve(), log_payload)
                print(f"JSON log written: {Path(args.log_json).expanduser().resolve()}")
            if args.log_jsonl:
                append_jsonl_log(Path(args.log_jsonl).expanduser().resolve(), log_payload)
                print(f"JSONL log appended: {Path(args.log_jsonl).expanduser().resolve()}")
            if args.close_task_tab:
                close_page_best_effort(page)
                page = None
            return log_payload
        result = get_publisher(args.platform).prepare(
            page,
            media_path,
            caption,
            args,
            content_check_action,
        )

        page.screenshot(path=str(screenshot_path), full_page=True)
        media_processing_ok = (
            not result.get("media_processing_required")
            or result.get("media_processing_confirmed")
        )
        result["status"] = (
            "PREPARED"
            if result.get("uploaded") and result.get("caption_filled") and media_processing_ok
            else "PARTIAL"
        )
        if result["status"] == "PARTIAL":
            partial_error_type, partial_error_message = classify_partial_result(result)
            result["error_type"] = partial_error_type
            result["error_message"] = partial_error_message
        result["screenshot"] = str(screenshot_path)
        result["dry_run"] = args.dry_run
        result["finished_at"] = datetime.now().isoformat(timespec="seconds")
        result["duration_seconds"] = duration_seconds_since(run_started_at)
        log_payload = {
            "plan": plan,
            "bitbrowser": {
                "health": health,
                "opened_profile": {
                    "profile_id": opened.profile_id,
                    "cdp_source": opened.cdp_source,
                },
                "tab_trace": tab_trace,
            },
            "result": result,
        }
        if args.trace_tabs and browser is not None:
            tab_trace["after_publish_step"] = snapshot_tabs(
                browser.contexts[0],
                page,
            )
            print(
                "Tab trace after publish step:",
                json.dumps(tab_trace["after_publish_step"], ensure_ascii=False, indent=2),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.log_json:
            write_json_log(Path(args.log_json).expanduser().resolve(), log_payload)
            print(f"JSON log written: {Path(args.log_json).expanduser().resolve()}")
        if args.log_jsonl:
            append_jsonl_log(Path(args.log_jsonl).expanduser().resolve(), log_payload)
            print(f"JSONL log appended: {Path(args.log_jsonl).expanduser().resolve()}")

        if args.dry_run:
            print("Dry run complete. The script intentionally did not click Publish/Post.")
        else:
            print("Non-dry-run currently still stops before final publish by design.")

        if args.pause:
            input("Press Enter after human check to close the browser connection...")

        if args.close_task_tab:
            close_page_best_effort(page)
            page = None

        return log_payload
    except Exception as exc:
        failure_payload = write_failure_logs(
            args,
            plan,
            type(exc).__name__,
            str(exc),
            page=page,
            screenshot_path=screenshot_path,
        )
        args._failure_logged_by_single = True
        if getattr(args, "write_plan_status", False) and getattr(args, "plan_csv_path", None):
            write_failure_plan_status_from_payload(args.plan_csv_path, failure_payload)
        raise
    finally:
        if browser is not None and args.close_profile:
            browser.close()
        if pw is not None:
            pw.stop()
        if args.close_profile:
            time.sleep(1)
            bit.close_profile(profile_id)


def run_plan(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan_csv).expanduser().resolve()
    allowed_statuses = {
        item.strip().upper()
        for item in (args.include_status or "READY").split(",")
        if item.strip()
    }
    entries = [
        entry
        for entry in load_publish_plan(plan_path)
        if (entry.status.strip().upper() if entry.status else "READY") in allowed_statuses
    ]
    if args.only_publish_id:
        wanted = {item.strip() for item in args.only_publish_id.split(",") if item.strip()}
        entries = [entry for entry in entries if entry.publish_id in wanted]
    if args.only_platform:
        entries = [entry for entry in entries if entry.platform == args.only_platform]
    if args.limit is not None:
        entries = entries[: args.limit]
    if not entries:
        raise SystemExit(
            f"No publish plan rows found for statuses {sorted(allowed_statuses)}: {plan_path}"
        )

    print(f"Publish plan: {plan_path}")
    print(f"Rows selected: {len(entries)}")

    exit_code = 0
    for index, entry in enumerate(entries, start=1):
        task_started_at = datetime.now().isoformat(timespec="seconds")
        if entry.platform not in PUBLISHERS:
            print(
                f"SKIP {entry.publish_id}: unsupported platform={entry.platform}",
                file=sys.stderr,
            )
            append_plan_failure(args, plan_path, entry, "UNSUPPORTED_PLATFORM", "Unsupported platform")
            exit_code = 1
            continue
        if not entry.media_path:
            print(f"SKIP {entry.publish_id}: media_path is empty", file=sys.stderr)
            append_plan_failure(args, plan_path, entry, "EMPTY_MEDIA_PATH", "media_path is empty")
            exit_code = 1
            continue

        media_path = resolve_path_maybe_relative(entry.media_path, plan_path.parent)
        caption = entry.build_caption()
        task_args = argparse.Namespace(**vars(args))
        task_args.publish_id = entry.publish_id
        task_args.client_id = entry.client_id
        task_args.product_id = entry.product_id
        task_args.platform = entry.platform
        task_args.content_type = entry.content_type
        task_args.account_key = entry.account_key or args.account_key
        task_args.profile_id = args.profile_id or entry.browser_profile_id or None
        task_args.media = str(media_path)
        task_args.caption = caption
        task_args.title = entry.title
        task_args.tracking_url = entry.tracking_url
        task_args.attribution_token = entry.attribution_token
        task_args.scheduled_at = entry.scheduled_at
        task_args.facebook_content_mode = entry.facebook_content_mode or args.facebook_content_mode
        task_args.facebook_composer_url = entry.composer_url or args.facebook_composer_url
        task_args.delivery_csv = None
        task_args.plan_dir = plan_path.parent
        task_args.plan_csv_path = plan_path
        task_args.plan_row_status = entry.status
        task_args.from_plan = True
        task_args.screenshot = (
            str(default_screenshot_path(entry.platform, entry.publish_id))
            if args.screenshot == DEFAULT_SCREENSHOT
            else args.screenshot
        )
        task_args.log_jsonl = args.log_jsonl
        if args.log_json:
            log_path = Path(args.log_json).expanduser()
            if len(entries) > 1 or log_path.suffix.lower() != ".json":
                log_path = log_path / f"{entry.publish_id}.json"
            task_args.log_json = str(log_path)

        print(f"[{index}/{len(entries)}] {entry.publish_id} {entry.platform} {media_path}")
        try:
            payload = run_single(task_args)
            if args.print_plan and args.log_jsonl:
                payload["plan"]["plan_csv"] = str(plan_path)
                payload["plan"]["plan_row_status"] = entry.status
                payload["result"]["status"] = "PLANNED"
                payload["result"]["finished_at"] = datetime.now().isoformat(timespec="seconds")
                append_jsonl_log(Path(args.log_jsonl).expanduser().resolve(), payload)
            if args.write_plan_status and not args.print_plan:
                updated = write_plan_status_from_payload(plan_path, payload)
                print(
                    "Publish plan status updated:",
                    json.dumps(updated, ensure_ascii=False),
                )
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if code != 0:
                exit_code = code
                append_plan_failure(
                    args,
                    plan_path,
                    entry,
                    "SYSTEM_EXIT",
                    str(exc),
                    task_started_at=task_started_at,
                    media_path=str(media_path),
                )
            if not args.continue_on_error:
                raise
        except Exception as exc:
            print(f"ERROR {entry.publish_id}: {exc}", file=sys.stderr)
            exit_code = 1
            if not getattr(task_args, "_failure_logged_by_single", False):
                append_plan_failure(
                    args,
                    plan_path,
                    entry,
                    type(exc).__name__,
                    str(exc),
                    task_started_at=task_started_at,
                    media_path=str(media_path),
                )
            if not args.continue_on_error:
                raise

    return exit_code


def run(args: argparse.Namespace) -> int:
    if args.generate_plan:
        return generate_publish_plan(args)
    if args.summarize_log_jsonl:
        summary_csv = Path(args.summary_csv).expanduser().resolve()
        rows = write_summary_csv(
            Path(args.summarize_log_jsonl).expanduser().resolve(),
            summary_csv,
            include_history=args.summary_include_history,
        )
        print(f"Publish summary written: {summary_csv}")
        print(f"Rows: {len(rows)}")
        return 0
    if args.backfill_publish_id:
        backfill_manual_publish(args)
        return 0
    if args.clean_blank_tabs:
        clean_blank_tabs(args)
        return 0
    if args.plan_csv:
        return run_plan(args)
    if not args.platform:
        raise SystemExit("--platform is required unless --plan-csv is provided.")
    if not args.media:
        raise SystemExit("--media is required unless --plan-csv is provided.")
    run_single(args)
    return 0


def backfill_manual_publish(args: argparse.Namespace) -> None:
    if not args.plan_csv:
        raise SystemExit("--plan-csv is required when using --backfill-publish-id.")

    status = args.backfill_status
    if status == "PUBLISHED_MANUAL" and not args.post_url:
        raise SystemExit("--post-url is required for PUBLISHED_MANUAL backfill.")

    plan_path = Path(args.plan_csv).expanduser().resolve()
    checked_at = datetime.now().isoformat(timespec="seconds")
    updates = {
        "status": status,
        "last_result_status": status,
        "last_result_at": checked_at,
        "post_url": args.post_url or "",
        "published_at": args.published_at or (checked_at if status == "PUBLISHED_MANUAL" else ""),
        "manual_operator": args.manual_operator or "",
        "manual_checked_at": checked_at,
        "manual_note": args.manual_note or "",
    }
    updated = update_publish_plan_row(plan_path, args.backfill_publish_id, updates)

    payload = {
        "plan": {
            "publish_id": args.backfill_publish_id,
            "plan_csv": str(plan_path),
        },
        "result": {
            "status": status,
            "post_url": args.post_url or "",
            "published_at": updates["published_at"],
            "manual_operator": args.manual_operator or "",
            "manual_checked_at": checked_at,
            "manual_note": args.manual_note or "",
            "finished_at": checked_at,
        },
    }
    if args.log_jsonl:
        append_jsonl_log(Path(args.log_jsonl).expanduser().resolve(), payload)
        print(f"JSONL log appended: {Path(args.log_jsonl).expanduser().resolve()}")

    print("Manual publish backfilled:", json.dumps(updated, ensure_ascii=False))


def clean_blank_tabs(args: argparse.Namespace) -> None:
    profile_id = args.profile_id
    if not profile_id and args.account_key:
        ledger_path = Path(args.account_ledger).expanduser().resolve() if args.account_ledger else None
        if ledger_path is not None:
            account_entry = select_account_entry(
                load_account_ledger(ledger_path),
                args.platform or "",
                account_key=args.account_key,
            )
            if account_entry is not None:
                profile_id = account_entry.profile_id
    if not profile_id:
        raise SystemExit("--profile-id is required for --clean-blank-tabs unless resolved from --account-ledger and --account-key.")

    bit = BitBrowserClient(args.bit_api)
    health = bit.health()
    opened = bit.open_profile(profile_id)
    pw = None
    browser = None
    try:
        pw, browser, context = connect_browser_context(opened.cdp_url)
        before = snapshot_tabs(context)
        closed = close_blank_tabs(context, keep_one_blank=args.keep_one_blank_tab)
        after = snapshot_tabs(context)
        payload = {
            "action": "clean_blank_tabs",
            "profile_id": profile_id,
            "health": health,
            "opened_profile": {
                "profile_id": opened.profile_id,
                "cdp_source": opened.cdp_source,
            },
            "before": before,
            "closed_count": len(closed),
            "after": after,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if args.log_json:
            write_json_log(Path(args.log_json).expanduser().resolve(), payload)
        if args.log_jsonl:
            append_jsonl_log(Path(args.log_jsonl).expanduser().resolve(), payload)
    finally:
        if pw is not None:
            pw.stop()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BitBrowser assisted publishing demo")
    parser.add_argument(
        "--one-click",
        action="store_true",
        help=(
            "Run operator mode: discover the active publish_plan.csv, process READY rows, "
            "write logs/status, keep prepared tabs open, and stop before final publish."
        ),
    )
    parser.add_argument(
        "--generate-plan",
        action="store_true",
        help=(
            "Generate publish_plan.csv from a delivery directory, delivery CSV, media files, "
            "and account ledger, then exit."
        ),
    )
    parser.add_argument(
        "--delivery-dir",
        help=(
            "Delivery package directory for --generate-plan. Defaults to the directory of "
            "--delivery-csv, or the current working directory."
        ),
    )
    parser.add_argument(
        "--output-plan-csv",
        help="Output path for --generate-plan. Defaults to publish_plan.csv in the delivery directory.",
    )
    parser.add_argument(
        "--overwrite-plan",
        action="store_true",
        help="Allow --generate-plan to overwrite an existing publish_plan.csv.",
    )
    parser.add_argument(
        "--plan-video-platforms",
        default="tiktok",
        help="Comma-separated platforms generated for video files. Default: tiktok. Use none to disable.",
    )
    parser.add_argument(
        "--plan-image-platforms",
        default="facebook",
        help="Comma-separated platforms generated for image files. Default: facebook. Use none to disable.",
    )
    parser.add_argument(
        "--plan-repeat",
        type=int,
        default=1,
        help="Generate this many tasks for each media/platform pair. Default: 1.",
    )
    parser.add_argument(
        "--plan-client-id",
        default="",
        help="client_id written to generated publish_plan.csv rows.",
    )
    parser.add_argument(
        "--plan-product-id",
        default="",
        help="product_id written to generated publish_plan.csv rows.",
    )
    parser.add_argument(
        "--plan-operator",
        default="",
        help="operator written to generated publish_plan.csv rows.",
    )
    parser.add_argument(
        "--plan-initial-status",
        default="READY",
        help="Initial status for generated rows. Default: READY.",
    )
    parser.add_argument(
        "--plan-note",
        default="",
        help="note written to generated publish_plan.csv rows.",
    )
    parser.add_argument(
        "--plan-attribution-prefix",
        default="",
        help="Optional attribution token prefix for generated rows.",
    )
    parser.add_argument(
        "--plan-scheduled-start",
        default="",
        help="Optional ISO start time for scheduled_at, e.g. 2026-08-14T10:00:00.",
    )
    parser.add_argument(
        "--plan-interval-minutes",
        type=int,
        default=30,
        help="Minute interval between generated scheduled_at values. Default: 30.",
    )
    parser.add_argument(
        "--plan-facebook-video-mode",
        choices=FACEBOOK_CONTENT_MODES,
        default="post",
        help=(
            "facebook_content_mode written for generated Facebook video rows. "
            "Default: post. Use reel/story only after the target entry is manually verified."
        ),
    )
    parser.add_argument(
        "--plan-facebook-video-composer-url",
        default="",
        help=(
            "Optional composer_url written for generated Facebook video rows, e.g. a "
            "manually verified Business Suite Reels composer URL."
        ),
    )
    parser.add_argument("--platform", choices=["tiktok", "facebook"])
    parser.add_argument("--publish-id", default="", help="Optional publish task ID for logs/screenshots")
    parser.add_argument("--client-id", default="", help="Optional client ID for logs and summaries")
    parser.add_argument("--product-id", default="", help="Optional product/SKU ID for logs and summaries")
    parser.add_argument("--content-type", default="", help="Optional content type, e.g. video/image")
    parser.add_argument("--profile-id", help="BitBrowser profile/window ID")
    parser.add_argument("--account-key", help="Account key in the optional account ledger")
    parser.add_argument("--media", help="Video or image path")
    parser.add_argument("--title", default="", help="Optional title for logs and summaries")
    parser.add_argument("--caption", help="Caption/post text")
    parser.add_argument("--tracking-url", default="", help="Optional tracking URL for logs and summaries")
    parser.add_argument("--attribution-token", default="", help="Optional attribution token for logs and summaries")
    parser.add_argument("--scheduled-at", default="", help="Optional scheduled time for logs and summaries")
    parser.add_argument("--screenshot", default=DEFAULT_SCREENSHOT)
    parser.add_argument("--bit-api", default=DEFAULT_BIT_API)
    parser.add_argument(
        "--plan-csv",
        help="Optional publish plan CSV. When provided, READY rows are executed sequentially.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of READY plan rows to process. Useful for safe tests.",
    )
    parser.add_argument(
        "--only-publish-id",
        help="Comma-separated publish_id filter for plan CSV mode.",
    )
    parser.add_argument(
        "--only-platform",
        choices=["tiktok", "facebook"],
        help="Platform filter for plan CSV mode.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue with later plan rows after one row fails.",
    )
    parser.add_argument(
        "--include-status",
        default="READY",
        help=(
            "Comma-separated plan row statuses to execute in plan mode. "
            "Default: READY. Use READY,PARTIAL to retry partial rows."
        ),
    )
    parser.add_argument(
        "--write-plan-status",
        action="store_true",
        help=(
            "Write PREPARED/PARTIAL/FAILED and screenshot/error fields back to the "
            "publish plan CSV. Off by default so test runs do not mutate operator sheets."
        ),
    )
    parser.add_argument(
        "--delivery-csv",
        help="Optional delivery CSV path; if omitted, the script looks for 矩阵投放文案对照表.csv near the media file",
    )
    parser.add_argument(
        "--account-ledger",
        help="Optional account ledger CSV path; if omitted, the script looks for 账号环境台账.csv near the media file",
    )
    parser.add_argument(
        "--upload-wait-ms",
        type=int,
        default=DEFAULT_UPLOAD_WAIT_MS,
        help="How long to wait for the platform file input after opening composer",
    )
    parser.add_argument(
        "--facebook-upload-mode",
        choices=FACEBOOK_UPLOAD_MODES,
        default="auto",
        help=(
            "Facebook upload strategy. Default: auto, which tries input first and then a "
            "Playwright-controlled file chooser. input-only never opens a native file chooser."
        ),
    )
    parser.add_argument(
        "--facebook-content-mode",
        choices=FACEBOOK_CONTENT_MODES,
        default="post",
        help="Facebook target surface for checkpoints/logs. Default: post.",
    )
    parser.add_argument(
        "--facebook-composer-url",
        default=DEFAULT_FACEBOOK_COMPOSER_URL,
        help=(
            "Facebook composer URL to open. Plan CSV composer_url overrides this per row. "
            f"Default: {DEFAULT_FACEBOOK_COMPOSER_URL}"
        ),
    )
    parser.add_argument(
        "--content-check-action",
        choices=CONTENT_CHECK_ACTIONS,
        default=None,
        help=(
            "What to do when TikTok asks to turn on automatic content checks. "
            "Default pauses because this is an account-level setting."
        ),
    )
    parser.add_argument(
        "--tab-mode",
        choices=TAB_MODES,
        default="new",
        help=(
            "Which browser tab to use after connecting over CDP. Default: new, so "
            "each publishing task opens a fresh tab and does not overwrite an existing draft. "
            "Use reuse-first only for legacy debugging."
        ),
    )
    parser.add_argument(
        "--trace-tabs",
        action="store_true",
        help="Print and log sanitized tab snapshots before and after selecting the task tab.",
    )
    parser.add_argument(
        "--stop-after-connect",
        action="store_true",
        help="Open the profile, connect to CDP, trace tabs, and exit before any upload or composer action.",
    )
    parser.add_argument(
        "--close-task-tab",
        action="store_true",
        help="Close only the task tab after the run. The BitBrowser profile remains open unless --close-profile is also set.",
    )
    parser.add_argument(
        "--clean-blank-tabs",
        action="store_true",
        help="Open/connect the profile and close about:blank tabs. Does not run a publish task.",
    )
    parser.add_argument(
        "--keep-one-blank-tab",
        action="store_true",
        help="With --clean-blank-tabs, leave one about:blank tab open.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Kept for readability. The example always stops before final publish.",
    )
    parser.add_argument(
        "--print-plan",
        action="store_true",
        help="Resolve media, delivery CSV, account ledger, and caption, then exit before opening BitBrowser.",
    )
    parser.add_argument(
        "--log-json",
        help="Optional JSON result log path. Written after the browser preparation step completes.",
    )
    parser.add_argument(
        "--log-jsonl",
        help=(
            "Optional JSONL log path for append-only publish logs. "
            f"Suggested: {DEFAULT_LOG_JSONL}"
        ),
    )
    parser.add_argument(
        "--summarize-log-jsonl",
        help="Read a publish JSONL log and export an operator-friendly summary CSV.",
    )
    parser.add_argument(
        "--summary-csv",
        default=DEFAULT_SUMMARY_CSV,
        help=f"Output CSV for --summarize-log-jsonl. Default: {DEFAULT_SUMMARY_CSV}",
    )
    parser.add_argument(
        "--summary-include-history",
        action="store_true",
        help="Export every JSONL event instead of only the latest event per publish_id.",
    )
    parser.add_argument(
        "--backfill-publish-id",
        help="Manually backfill a publish_id after the operator has published or rejected it.",
    )
    parser.add_argument(
        "--backfill-status",
        choices=MANUAL_BACKFILL_STATUSES,
        default="PUBLISHED_MANUAL",
        help="Manual backfill status. Defaults to PUBLISHED_MANUAL.",
    )
    parser.add_argument("--post-url", help="Published post URL for manual backfill.")
    parser.add_argument("--published-at", help="Published time for manual backfill.")
    parser.add_argument("--manual-operator", help="Operator name for manual backfill.")
    parser.add_argument("--manual-note", help="Manual note for backfill.")
    parser.add_argument("--pause", action="store_true", help="Pause before closing connection")
    parser.add_argument("--close-profile", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    configure_utf8_stdio()
    try:
        args = parse_args(argv)
        if args.one_click or not argv:
            args = configure_one_click(args)
        return run(args)
    except (BitBrowserError, requests.RequestException) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
