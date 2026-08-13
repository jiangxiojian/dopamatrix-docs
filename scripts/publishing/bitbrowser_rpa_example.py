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
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


DEFAULT_BIT_API = "http://127.0.0.1:54345"
DEFAULT_TIKTOK_UPLOAD_URL = "https://www.tiktok.com/upload?lang=en"
DEFAULT_FACEBOOK_COMPOSER_URL = "https://business.facebook.com/latest/composer"
DEFAULT_UPLOAD_WAIT_MS = 60_000
DEFAULT_SCREENSHOT = "output/publish-rpa/screenshot.png"
DEFAULT_LOG_JSONL = "output/publish-rpa/publish_logs.jsonl"
DEFAULT_SUMMARY_CSV = "output/publish-rpa/publish_summary.csv"
CONTENT_CHECK_ACTIONS = ("pause", "enable", "cancel")
MANUAL_BACKFILL_STATUSES = ("PUBLISHED_MANUAL", "REJECTED_MANUAL", "PREPARED", "FAILED")
SUMMARY_FIELDS = [
    "publish_id",
    "client_id",
    "product_id",
    "platform",
    "content_type",
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
    "post_url",
    "published_at",
    "manual_operator",
    "manual_checked_at",
    "manual_note",
    "screenshot",
    "error_type",
    "error_message",
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
    rows = _read_csv_rows(csv_path)
    if not rows:
        raise BitBrowserError(f"Delivery CSV is empty: {csv_path}")

    media_name = media_path.name
    matched = None
    for row in rows:
        row_media_name = _first_nonempty(row, "视频文件名", "video_filename", "media", "media_name")
        if row_media_name == media_name:
            matched = row
            break

    if matched is None:
        if len(rows) == 1:
            matched = rows[0]
        else:
            available = ", ".join(
                _first_nonempty(row, "视频文件名", "video_filename", "media", "media_name") or "<empty>"
                for row in rows[:10]
            )
            raise BitBrowserError(
                "No delivery CSV row matched the media filename. "
                f"media={media_name}, csv={csv_path}, sample_rows={available}"
            )

    return DeliveryRecord(
        video_filename=_first_nonempty(matched, "视频文件名", "video_filename", "media", "media_name") or media_name,
        social_title=_first_nonempty(matched, "社交平台标题", "social_title", "title"),
        emotional_description=_first_nonempty(matched, "情绪化描述", "social_caption", "caption", "description"),
        hashtags=_first_nonempty(matched, "黄金标签", "social_hashtags", "hashtags", "tag"),
        tracking_link=_first_nonempty(matched, "追踪短链接", "tracking_link", "url", "link"),
        source_csv=str(csv_path),
        raw=matched,
    )


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
        ("矩阵投放文案对照表.csv", "delivery.csv", "publish_plan.csv"),
    )


def resolve_account_ledger(media_path: Path, explicit_csv: str | None) -> Path | None:
    if explicit_csv:
        return Path(explicit_csv).expanduser().resolve()
    return _discover_file_upwards(
        media_path.parent,
        ("账号环境台账.csv", "account-ledger.csv", "account_ledger.csv"),
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
            ("账号环境台账.csv", "account-ledger.csv", "account_ledger.csv"),
        )
        if found is not None:
            return found
    return resolve_account_ledger(media_path, explicit_csv)


def connect_page(cdp_url: str):
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
    page = context.pages[0] if context.pages else context.new_page()
    return pw, browser, page


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
        "[aria-label*='添加照片' i]",
        "[aria-label*='照片' i]",
        "[role='button']:has-text('Add photo/video')",
        "button:has-text('Add photo/video')",
        "div[role='button']:has-text('Add photo/video')",
        "span:has-text('Add photo/video')",
        "[aria-label*='Add photo' i]",
        "[aria-label*='photo' i]",
        "text=/Add photo\\/video/i",
        "text=/添加照片\\/视频/",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if locator.count() == 0:
                continue
            with page.expect_file_chooser(timeout=timeout_ms) as chooser_info:
                locator.first.click(timeout=5000)
            chooser_info.value.set_files(str(media_path))
            return True
        except Exception:
            continue
    return False


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
) -> dict[str, Any]:
    page.goto(DEFAULT_FACEBOOK_COMPOSER_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(5000)

    dismissed_popups = dismiss_safe_popups(page)
    uploaded = set_first_file_input(page, media_path, min(upload_wait_ms, 3000))
    used_file_chooser = False
    if not uploaded:
        uploaded = upload_via_facebook_media_button(page, media_path, upload_wait_ms)
        used_file_chooser = uploaded
    if uploaded:
        page.wait_for_timeout(5000)
    caption_filled = fill_text_best_effort(page, caption)

    return {
        "platform": "facebook",
        "url": page.url,
        "uploaded": uploaded,
        "caption_filled": caption_filled,
        "used_file_chooser": used_file_chooser,
        "dismissed_popups": dismissed_popups,
        "checkpoint": "请人工检查 Page 是否正确、图片/文案预览、发布或排期设置，然后手动点击发布。",
    }


def default_screenshot_path(platform: str, publish_id: str = "") -> Path:
    if publish_id:
        safe_publish_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", publish_id).strip("_")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return Path("output") / "publish-rpa" / f"{safe_publish_id}-{platform}-{timestamp}.png"
    return Path(DEFAULT_SCREENSHOT)


def classify_error(error_type: str, error_message: str, platform: str = "") -> str:
    haystack = f"{platform} {error_type} {error_message}".lower()
    if "unsupported platform" in haystack:
        return "UNSUPPORTED_PLATFORM"
    if "media file does not exist" in haystack or "empty_media_path" in haystack:
        return "MEDIA_PATH_INVALID"
    if "profile-id is required" in haystack or "publish_id not found" in haystack:
        return "PLAN_CONFIG_INVALID"
    if "playwright is not installed" in haystack:
        return "LOCAL_DEPENDENCY_MISSING"
    if "failed to establish a new connection" in haystack or "/health" in haystack:
        return "BITBROWSER_CONNECTION"
    if "failed to open the profile" in haystack or "did not return a cdp address" in haystack:
        return "BITBROWSER_PROFILE_OPEN"
    if "content checks" in haystack:
        return "ACCOUNT_SETTING_CHECK"
    if "verification" in haystack or "captcha" in haystack or "face" in haystack or "identity" in haystack:
        return "ACCOUNT_VERIFICATION"
    if "login" in haystack or "log in" in haystack or "sign in" in haystack:
        return "LOGIN_REQUIRED"
    if "timeout" in haystack:
        return "PLATFORM_TIMEOUT"
    return error_type or "UNKNOWN_ERROR"


def classify_partial_result(result: dict[str, Any]) -> tuple[str, str]:
    if not result.get("uploaded"):
        return "UPLOAD_NOT_CONFIRMED", "Media upload was not confirmed by the page."
    if not result.get("caption_filled"):
        return "CAPTION_NOT_FILLED", "Caption field was not filled."
    return "", ""


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
        "content_check_action": content_check_action,
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
    try:
        pw, browser, page = connect_page(opened.cdp_url)
        if args.platform == "tiktok":
            result = publish_tiktok(
                page,
                media_path,
                caption,
                args.upload_wait_ms,
                content_check_action,
            )
        elif args.platform == "facebook":
            result = publish_facebook(page, media_path, caption, args.upload_wait_ms)
        else:
            raise SystemExit(f"Unsupported platform: {args.platform}")

        page.screenshot(path=str(screenshot_path), full_page=True)
        result["status"] = (
            "PREPARED"
            if result.get("uploaded") and result.get("caption_filled")
            else "PARTIAL"
        )
        if result["status"] == "PARTIAL":
            partial_error_type, partial_error_message = classify_partial_result(result)
            result["error_type"] = partial_error_type
            result["error_message"] = partial_error_message
        result["screenshot"] = str(screenshot_path)
        result["dry_run"] = args.dry_run
        result["finished_at"] = datetime.now().isoformat(timespec="seconds")
        log_payload = {
            "plan": plan,
            "bitbrowser": {
                "health": health,
                "opened_profile": {
                    "profile_id": opened.profile_id,
                    "cdp_source": opened.cdp_source,
                },
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

        if args.dry_run:
            print("Dry run complete. The script intentionally did not click Publish/Post.")
        else:
            print("Non-dry-run currently still stops before final publish by design.")

        if args.pause:
            input("Press Enter after human check to close the browser connection...")

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
    entries = [entry for entry in load_publish_plan(plan_path) if entry.is_ready()]
    if args.only_publish_id:
        wanted = {item.strip() for item in args.only_publish_id.split(",") if item.strip()}
        entries = [entry for entry in entries if entry.publish_id in wanted]
    if args.only_platform:
        entries = [entry for entry in entries if entry.platform == args.only_platform]
    if args.limit is not None:
        entries = entries[: args.limit]
    if not entries:
        raise SystemExit(f"No READY publish plan rows found: {plan_path}")

    print(f"Publish plan: {plan_path}")
    print(f"Ready rows selected: {len(entries)}")

    exit_code = 0
    for index, entry in enumerate(entries, start=1):
        task_started_at = datetime.now().isoformat(timespec="seconds")
        if entry.platform not in {"tiktok", "facebook"}:
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BitBrowser assisted publishing demo")
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
        "--content-check-action",
        choices=CONTENT_CHECK_ACTIONS,
        default=None,
        help=(
            "What to do when TikTok asks to turn on automatic content checks. "
            "Default pauses because this is an account-level setting."
        ),
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
        return run(parse_args(argv))
    except (BitBrowserError, requests.RequestException) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
