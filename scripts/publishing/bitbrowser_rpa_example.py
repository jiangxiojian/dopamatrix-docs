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
import multiprocessing as mp
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
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

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
DEFAULT_TASK_TIMEOUT_SECONDS = 600
FACEBOOK_FILE_CHOOSER_EVENT_WAIT_MS = 8_000
CONTENT_CHECK_ACTIONS = ("pause", "enable", "cancel")
TAB_MODES = ("new", "reuse-first")
FACEBOOK_UPLOAD_MODES = ("auto", "input-only", "file-chooser")
FACEBOOK_CONTENT_MODES = ("post", "reel", "story")
MANUAL_BACKFILL_STATUSES = ("PUBLISHED_MANUAL", "REJECTED_MANUAL", "PREPARED", "FAILED")
SUPPORTED_PLATFORMS = ("tiktok", "facebook")
SAFE_POPUP_BUTTON_SELECTORS = (
    "button:has-text('Got it')",
    "button:has-text('Not now')",
    "button:has-text('Maybe later')",
)
SAFE_CANCEL_DIALOG_PATTERNS = (
    r"turn on notifications",
    r"allow notifications",
    r"sync contacts",
    r"save your login info",
)
PLATFORM_CODES = {
    "tiktok": "TK",
    "facebook": "FB",
}
ERROR_ACTION_LABELS = {
    "DONE": "已完成",
    "HUMAN_PUBLISH_CHECK": "人工检查并发布",
    "NO_ACTION": "无需处理",
    "PENDING": "等待执行",
    "RETRY_TASK": "重试任务",
    "CHECK_LOCAL_BROWSER": "检查本机浏览器",
    "CHECK_PROXY": "检查代理",
    "HUMAN_ACCOUNT_CHECK": "人工检查账号",
    "CHECK_PAGE_ACCESS": "检查 Page 权限",
    "FIX_PLAN": "修正计划表",
    "FIX_MEDIA": "修正素材",
    "PAUSE_ACCOUNT": "暂停账号",
    "RETRY_OR_MANUAL_CHECK": "重试或人工检查",
    "HUMAN_REVIEW": "人工判断",
}
TIKTOK_POST_QUERY_ID_KEYS = (
    "item_id",
    "itemId",
    "item_id_str",
    "itemIdStr",
    "video_id",
    "videoId",
    "aweme_id",
    "awemeId",
    "share_item_id",
    "content_id",
)
TIKTOK_USERNAME_QUERY_KEYS = (
    "username",
    "user",
    "handle",
    "author",
    "authorUsername",
    "author_unique_id",
    "unique_id",
    "uniqueId",
)
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
    "error_action",
    "error_action_label",
    "error_message",
    "post_url",
    "platform_post_id",
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
    "platform_post_id",
    "published_at",
    "manual_operator",
    "manual_checked_at",
    "manual_note",
    "screenshot",
    "error_type",
    "error_action",
    "error_action_label",
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
    "platform_post_id",
    "published_at",
    "manual_operator",
    "manual_checked_at",
    "manual_note",
    "error_type",
    "error_action",
    "error_action_label",
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
    "platform_post_id": ("platform_post_id", "平台post_id", "平台帖子ID", "post_id"),
    "published_at": ("published_at", "发布时间"),
    "manual_operator": ("manual_operator", "人工操作人"),
    "manual_checked_at": ("manual_checked_at", "人工确认时间"),
    "manual_note": ("manual_note", "人工备注"),
    "screenshot": ("result_screenshot", "结果截图"),
    "error_type": ("error_type", "错误类型"),
    "error_action": ("error_action", "处理建议", "处置建议"),
    "error_action_label": ("error_action_label", "处理建议说明", "处置建议说明"),
    "error_message": ("error_message", "错误信息"),
}
PLAN_STATUS_COLUMNS = {
    "publish_id": ("发布ID", "id"),
    "status": ("状态",),
    "last_result_status": ("最后结果状态",),
    "last_result_at": ("最后结果时间",),
    "result_screenshot": ("结果截图",),
    "error_type": ("错误类型",),
    "error_action": ("处理建议", "处置建议"),
    "error_action_label": ("处理建议说明", "处置建议说明"),
    "error_message": ("错误信息",),
    "post_url": ("帖子链接", "发布链接"),
    "platform_post_id": ("平台post_id", "平台帖子ID", "post_id"),
    "published_at": ("发布时间",),
    "manual_operator": ("人工操作人",),
    "manual_checked_at": ("人工确认时间",),
    "manual_note": ("人工备注",),
}


class BitBrowserError(RuntimeError):
    pass


class TaskTimeoutError(BitBrowserError):
    def __init__(self, publish_id: str, timeout_seconds: int) -> None:
        super().__init__(
            f"Plan row {publish_id} exceeded hard timeout of {timeout_seconds} seconds."
        )
        self.publish_id = publish_id
        self.timeout_seconds = timeout_seconds


class ChildTaskError(BitBrowserError):
    def __init__(self, error_type: str, error_message: str) -> None:
        super().__init__(f"{error_type}: {error_message}")
        self.error_type = error_type
        self.error_message = error_message


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
    if not args.task_timeout_seconds:
        args.task_timeout_seconds = DEFAULT_TASK_TIMEOUT_SECONDS
    if not args.log_jsonl:
        args.log_jsonl = str(project_root() / DEFAULT_LOG_JSONL)

    print("One-click prepare mode")
    print(f"Plan: {plan_path}")
    print(f"Per-task hard timeout: {args.task_timeout_seconds}s")
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


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def normalize_platform_name(platform: str) -> str:
    key = (platform or "").strip().lower()
    return {"fb": "facebook", "tt": "tiktok", "tk": "tiktok"}.get(key, key)


def _empty_post_candidate() -> dict[str, Any]:
    return {
        "post_url": "",
        "platform_post_id": "",
        "source": "",
        "tab_index": 0,
        "tab_url": "",
        "text": "",
        "score": -1,
    }


def _post_candidate_score(source: str, tab_url: str) -> int:
    key = source.strip().lower()
    score = {
        "tab_url": 320,
        "canonical": 260,
        "og:url": 250,
        "twitter:url": 240,
        "anchor": 200,
        "link": 180,
        "text:tiktok_public_url": 230,
        "text:tiktok_item_id": 220,
        "text:facebook_public_url": 230,
        "text:facebook_business_content_id": 225,
    }.get(key, 150)
    if "business_content_id" in key:
        score = max(score, 225)
    tab_url_lower = tab_url.lower()
    if "latest/composer" in tab_url_lower or "/composer" in tab_url_lower:
        score -= 70
    if "/upload" in tab_url_lower or "/draft" in tab_url_lower:
        score -= 30
    return score


def _facebook_candidate_time_delta_seconds(text: str, checked_at: datetime) -> int | None:
    match = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", text or "")
    if not match:
        return None
    candidate_at = checked_at.replace(
        hour=int(match.group(1)),
        minute=int(match.group(2)),
        second=0,
        microsecond=0,
    )
    if candidate_at > checked_at + timedelta(minutes=5):
        candidate_at -= timedelta(days=1)
    delta_seconds = int((checked_at - candidate_at).total_seconds())
    if delta_seconds < -300:
        return None
    return max(0, delta_seconds)


def _post_candidate_sort_key(
    item: dict[str, Any],
    platform: str,
    checked_at: datetime | None = None,
) -> tuple[Any, ...]:
    score = -int(item.get("score", 0))
    if platform == "facebook" and checked_at is not None:
        delta_seconds = item.get("time_delta_seconds")
        if delta_seconds in (None, ""):
            delta_seconds = _facebook_candidate_time_delta_seconds(
                str(item.get("text", "")),
                checked_at,
            )
        missing_time = 1 if delta_seconds is None else 0
        delta_value = int(delta_seconds) if delta_seconds is not None else 10**9
        return (
            score,
            missing_time,
            delta_value,
            int(item.get("tab_index", 0)),
            item.get("post_url", ""),
        )
    return (
        score,
        int(item.get("tab_index", 0)),
        item.get("post_url", ""),
    )


def _candidate_url_parts(url: str) -> tuple[str, str, str, str]:
    cleaned = str(url or "").strip()
    if not cleaned:
        return "", "", "", ""
    if cleaned.startswith("//"):
        cleaned = f"https:{cleaned}"
    try:
        parts = urlsplit(cleaned)
    except Exception:
        return "", "", "", ""
    return parts.scheme or "https", parts.netloc.lower(), parts.path, parts.query


def _first_query_value(query_map: dict[str, list[str]], keys: tuple[str, ...]) -> str:
    for key in keys:
        values = query_map.get(key, [])
        if values and values[0].strip():
            return values[0].strip()
    lowered = {key.lower(): values for key, values in query_map.items()}
    for key in keys:
        values = lowered.get(key.lower(), [])
        if values and values[0].strip():
            return values[0].strip()
    return ""


def _clean_tiktok_post_id(value: str) -> str:
    match = re.search(r"\b(\d{8,})\b", str(value or ""))
    return match.group(1) if match else ""


def _clean_tiktok_username(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", cleaned):
        return ""
    return cleaned


def _tiktok_username_from_path(path: str) -> str:
    match = re.search(r"/@([^/?#]+)/", path, re.IGNORECASE)
    if not match:
        return ""
    return _clean_tiktok_username(match.group(1))


def tiktok_post_id_from_query(query: str) -> str:
    query_map = parse_qs(query, keep_blank_values=True)
    return _clean_tiktok_post_id(_first_query_value(query_map, TIKTOK_POST_QUERY_ID_KEYS))


def tiktok_username_from_query(query: str) -> str:
    query_map = parse_qs(query, keep_blank_values=True)
    return _clean_tiktok_username(_first_query_value(query_map, TIKTOK_USERNAME_QUERY_KEYS))


def tiktok_public_url_from_parts(scheme: str, netloc: str, path: str, query: str) -> str:
    post_id = tiktok_post_id_from_query(query)
    if not post_id:
        return ""
    username = _tiktok_username_from_path(path) or tiktok_username_from_query(query)
    if username:
        return f"https://www.tiktok.com/@{username}/video/{post_id}"
    return f"https://www.tiktok.com/player/v1/{post_id}"


def extract_platform_post_id(url: str, platform: str) -> str:
    platform_key = normalize_platform_name(platform)
    scheme, netloc, path, query = _candidate_url_parts(url)
    if not scheme or not netloc:
        return ""

    if platform_key == "tiktok":
        if "tiktok.com" not in netloc:
            return ""
        match = re.search(r"/(?:@[^/?#]+/)?(?:video|photo)/(\d+)", path, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r"/v/(\d+)", path, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r"/player/v1/(\d+)", path, re.IGNORECASE)
        if match:
            return match.group(1)
        post_id = tiktok_post_id_from_query(query)
        if post_id:
            return post_id
        return ""

    if platform_key == "facebook":
        if "business.facebook.com" in netloc:
            return ""
        query_map = parse_qs(query, keep_blank_values=True)
        for pattern in (
            r"/posts/([^/?#]+)",
            r"/reels?/([^/?#]+)",
            r"/videos/([^/?#]+)",
            r"/photos/(?:[^/?#]+/)?([^/?#]+)",
        ):
            match = re.search(pattern, path, re.IGNORECASE)
            if match:
                return match.group(1)
        for key in ("story_fbid", "fbid", "v"):
            values = query_map.get(key, [])
            if values and values[0].strip():
                return values[0].strip()
        return ""

    return ""


def normalize_post_url(url: str, platform: str) -> str:
    platform_key = normalize_platform_name(platform)
    scheme, netloc, path, query = _candidate_url_parts(url)
    if not scheme or not netloc:
        return ""

    path = re.sub(r"/{2,}", "/", path)
    path = path.rstrip("/") or "/"
    query_map = parse_qs(query, keep_blank_values=True)

    if platform_key == "tiktok":
        if "tiktok.com" not in netloc:
            return ""
        if not extract_platform_post_id(url, platform_key):
            return ""
        if re.search(r"/(?:@[^/?#]+/)?(?:video|photo)/(\d+)", path, re.IGNORECASE):
            return urlunsplit((scheme, netloc, path, "", ""))
        if re.search(r"/(?:v|player/v1)/(\d+)", path, re.IGNORECASE):
            return urlunsplit((scheme, netloc, path, "", ""))
        public_url = tiktok_public_url_from_parts(scheme, netloc, path, query)
        if public_url:
            return public_url
        return urlunsplit((scheme, netloc, path, "", ""))

    if platform_key == "facebook":
        if "business.facebook.com" in netloc:
            return ""
        lower_path = path.lower()
        if any(keyword in lower_path for keyword in ("/composer", "latest/composer", "/stories/create")):
            return ""
        post_id = extract_platform_post_id(url, platform_key)
        if not post_id:
            return ""
        if (
            (lower_path.endswith("story.php") or lower_path.endswith("permalink.php"))
            and query_map.get("story_fbid")
            and query_map.get("id")
        ):
            query_text = urlencode(
                [("story_fbid", query_map["story_fbid"][0]), ("id", query_map["id"][0])],
                doseq=False,
            )
            return urlunsplit((scheme, netloc, "/permalink.php", query_text, ""))
        if lower_path.endswith("photo.php") and query_map.get("fbid") and query_map.get("id"):
            query_text = urlencode(
                [("fbid", query_map["fbid"][0]), ("id", query_map["id"][0])],
                doseq=False,
            )
            return urlunsplit((scheme, netloc, "/photo.php", query_text, ""))
        if lower_path.endswith("/watch") and query_map.get("v"):
            query_text = urlencode([("v", query_map["v"][0])], doseq=False)
            return urlunsplit((scheme, netloc, path, query_text, ""))
        return urlunsplit((scheme, netloc, path, "", ""))

    return ""


def facebook_business_content_candidate(url: str, fallback_page_id: str = "") -> str:
    scheme, netloc, path, query = _candidate_url_parts(url)
    if "business.facebook.com" not in netloc:
        return ""
    lower_path = path.lower()
    if "object_insights" not in lower_path and "/insights/" not in lower_path:
        return ""
    query_map = parse_qs(query, keep_blank_values=True)
    content_id = (query_map.get("content_id") or [""])[0].strip()
    if not content_id:
        return ""
    page_id = (query_map.get("asset_id") or [fallback_page_id])[0].strip()
    if page_id:
        return f"https://www.facebook.com/{page_id}/posts/{content_id}"
    return f"https://www.facebook.com/{content_id}"


def collect_post_url_candidates(page: Any, platform: str, tab_index: int) -> list[dict[str, Any]]:
    platform_key = normalize_platform_name(platform)
    tab_url = sanitize_tab_url(getattr(page, "url", ""))
    tab_query = parse_qs(urlsplit(getattr(page, "url", "") or "").query, keep_blank_values=True)
    fallback_facebook_page_id = (tab_query.get("asset_id") or [""])[0].strip()
    candidates: list[dict[str, Any]] = []

    def add_candidate(url: str, source: str, text: str = "") -> None:
        if platform_key == "facebook":
            business_candidate = facebook_business_content_candidate(
                url,
                fallback_page_id=fallback_facebook_page_id,
            )
            if business_candidate:
                url = business_candidate
                source = f"{source}:business_content_id"
        normalized = normalize_post_url(url, platform_key)
        if not normalized:
            return
        post_id = extract_platform_post_id(normalized, platform_key)
        if not post_id:
            return
        candidate = {
            "post_url": normalized,
            "platform_post_id": post_id,
            "source": source,
            "tab_index": tab_index,
            "tab_url": tab_url,
            "text": text.strip()[:160],
            "score": _post_candidate_score(source, tab_url),
        }
        candidates.append(candidate)

    add_candidate(getattr(page, "url", ""), "tab_url")

    try:
        items = page.evaluate(
            """() => {
              const items = [];
              const push = (source, url, text = '') => {
                if (!url) return;
                items.push({source, url: String(url), text: String(text || '')});
              };
              document.querySelectorAll('link[rel="canonical"][href]').forEach((node) => {
                push('canonical', node.href || node.getAttribute('href') || '', node.getAttribute('href') || '');
              });
              document.querySelectorAll('meta[property="og:url"][content], meta[name="twitter:url"][content]').forEach((node) => {
                push(node.getAttribute('property') || node.getAttribute('name') || 'meta', node.content || node.getAttribute('content') || '', node.content || '');
              });
              document.querySelectorAll('a[href]').forEach((node) => {
                push('anchor', node.href || node.getAttribute('href') || '', node.innerText || node.getAttribute('aria-label') || node.textContent || '');
              });
              if (location.hostname.includes('tiktok.com')) {
                const text = document.documentElement ? document.documentElement.innerText || '' : '';
                const html = document.documentElement ? document.documentElement.innerHTML || '' : '';
                const combined = `${text}\n${html}`;
                const publicUrlPattern = /https?:\/\/(?:www\.|m\.|vm\.)?tiktok\.com\/(?:@[\\w.-]+\/(?:video|photo)\/\\d+|v\/\\d+|player\/v1\/\\d+)/gi;
                for (const match of combined.matchAll(publicUrlPattern)) {
                  push('text:tiktok_public_url', match[0], match[0]);
                  if (items.length > 900) break;
                }
                const idPattern = /["']?(?:item_id|itemId|item_id_str|itemIdStr|video_id|videoId|aweme_id|awemeId|share_item_id|content_id)["']?\\s*[:=]\\s*["']?(\\d{8,})/gi;
                for (const match of combined.matchAll(idPattern)) {
                  push('text:tiktok_item_id', `https://www.tiktok.com/player/v1/${match[1]}`, match[0]);
                  if (items.length > 980) break;
                }
              }
              if (location.hostname.includes('facebook.com')) {
                const text = document.documentElement ? document.documentElement.innerText || '' : '';
                const html = document.documentElement ? document.documentElement.innerHTML || '' : '';
                const combined = `${text}\n${html}`
                  .replace(/&amp;/g, '&')
                  .replace(/\\\\u0026/g, '&')
                  .replace(/\\\\\\//g, '/');
                const publicUrlPattern = /https?:\/\/(?:www\.|m\.|web\.)?facebook\.com\/(?:[^"'<>\s]+\/posts\/\d+|(?:reel|reels|videos)\/\d+|[^"'<>\s]+\/videos\/\d+|[^"'<>\s]+\/photos\/(?:[^"'<>\s/]+\/)?\d+|story\.php\?[^"'<>\s]*story_fbid=\d+[^"'<>\s]*|permalink\.php\?[^"'<>\s]*story_fbid=\d+[^"'<>\s]*|photo\.php\?[^"'<>\s]*fbid=\d+[^"'<>\s]*|watch\/?\?[^"'<>\s]*v=\d+[^"'<>\s]*)/gi;
                for (const match of combined.matchAll(publicUrlPattern)) {
                  push('text:facebook_public_url', match[0], match[0]);
                  if (items.length > 900) break;
                }
                const businessContentPattern = /https?:\/\/business\.facebook\.com\/latest\/insights\/object_insights\/\?[^"'<>\s]*content_id=\d+[^"'<>\s]*/gi;
                for (const match of combined.matchAll(businessContentPattern)) {
                  push('text:facebook_business_content_id', match[0], match[0]);
                  if (items.length > 980) break;
                }
              }
              return items.slice(0, 1000);
            }"""
        )
    except Exception:
        items = []

    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            add_candidate(item.get("url", ""), str(item.get("source", "anchor")), str(item.get("text", "")))

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        key = (candidate["post_url"], candidate["platform_post_id"])
        current = deduped.get(key)
        if current is None or candidate["score"] > current["score"]:
            deduped[key] = candidate
    return sorted(
        deduped.values(),
        key=lambda item: (-int(item.get("score", 0)), int(item.get("tab_index", 0)), item.get("post_url", "")),
    )


def detect_post_url_in_context(context: Any, platform: str) -> dict[str, Any]:
    checked_at = datetime.now().isoformat(timespec="seconds")
    checked_at_dt = datetime.fromisoformat(checked_at)
    platform_key = normalize_platform_name(platform)
    scanned_tabs = snapshot_tabs(context)
    candidates: list[dict[str, Any]] = []
    for tab_index, page in enumerate(context.pages, start=1):
        try:
            candidates.extend(collect_post_url_candidates(page, platform, tab_index))
        except Exception as exc:
            candidates.append(
                {
                    **_empty_post_candidate(),
                    "source": f"error:{type(exc).__name__}",
                    "tab_index": tab_index,
                    "tab_url": sanitize_tab_url(getattr(page, "url", "")),
                    "text": str(exc)[:160],
                }
            )

    viable = [item for item in candidates if item.get("post_url") and item.get("platform_post_id")]
    if platform_key == "facebook":
        for item in viable:
            delta_seconds = _facebook_candidate_time_delta_seconds(
                str(item.get("text", "")),
                checked_at_dt,
            )
            if delta_seconds is not None:
                item["time_delta_seconds"] = delta_seconds
    viable.sort(key=lambda item: _post_candidate_sort_key(item, platform_key, checked_at_dt))
    best = viable[0] if viable else _empty_post_candidate()
    best_result = {
        "detected": bool(viable),
        "checked_at": checked_at,
        "platform": platform_key,
        "post_url": best.get("post_url", ""),
        "platform_post_id": best.get("platform_post_id", ""),
        "published_at": checked_at if viable else "",
        "source": best.get("source", ""),
        "tab_index": best.get("tab_index", 0),
        "tab_url": best.get("tab_url", ""),
        "text": best.get("text", ""),
        "candidates": viable[:10],
        "scanned_tabs": scanned_tabs,
    }
    return best_result


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
    if not row.get("error_action"):
        row["error_action"] = recommend_error_action(row.get("error_type", ""), row.get("status", ""))
    if not row.get("error_action_label"):
        row["error_action_label"] = describe_error_action(row.get("error_action", ""))
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
    error_type = str(result.get("error_type") or "")
    return {
        "status": status,
        "last_result_status": status,
        "last_result_at": str(finished_at),
        "result_screenshot": str(result.get("screenshot") or ""),
        "error_type": error_type,
        "error_action": str(result.get("error_action") or recommend_error_action(error_type, status)),
        "error_action_label": str(
            result.get("error_action_label")
            or describe_error_action(str(result.get("error_action") or recommend_error_action(error_type, status)))
        ),
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


def find_publish_plan_entry(csv_path: Path, publish_id: str) -> PublishPlanEntry:
    for entry in load_publish_plan(csv_path):
        if entry.publish_id == publish_id:
            return entry
    raise BitBrowserError(f"publish_id not found in plan: {publish_id}")


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
        "platform_post_id": "",
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
    for _ in range(5):
        clicked_in_pass = False
        for selector in SAFE_POPUP_BUTTON_SELECTORS:
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
        for pattern in SAFE_CANCEL_DIALOG_PATTERNS:
            try:
                dialog = page.get_by_role("dialog").filter(has_text=re.compile(pattern, re.IGNORECASE))
                if dialog.count() == 0:
                    continue
                cancel = dialog.first.get_by_role("button", name=re.compile(r"^Cancel$", re.IGNORECASE))
                if cancel.count() == 0:
                    continue
                cancel.first.click(timeout=3000)
                clicked.append(f"dialog:{pattern}:Cancel")
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
    if "tasktimeouterror" in haystack or "hard timeout" in haystack or "task timeout" in haystack:
        return "TASK_TIMEOUT"
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
    if platform_key == "facebook" and "file chooser" in haystack and ("timeout" in haystack or "timed out" in haystack):
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


def recommend_error_action(error_type: str, status: str = "") -> str:
    error_key = (error_type or "").strip().upper()
    status_key = (status or "").strip().upper()
    if status_key == "PUBLISHED_MANUAL":
        return "DONE"
    if status_key in {"REJECTED_MANUAL", "SKIPPED"}:
        return "NO_ACTION"
    if status_key in {"READY", "PLANNED", "RUNNING"} and not error_key:
        return "PENDING"
    if status_key in {"FAILED", "PARTIAL"} and not error_key:
        return "HUMAN_REVIEW"
    if not error_key:
        if status_key == "PREPARED":
            return "HUMAN_PUBLISH_CHECK"
        return ""

    if error_key in {"TASK_TIMEOUT", "BROWSER_TARGET_CLOSED", "PLATFORM_TIMEOUT"}:
        return "RETRY_TASK"
    if error_key in {"BITBROWSER_CONNECTION", "BITBROWSER_PROFILE_OPEN", "LOCAL_DEPENDENCY_MISSING"}:
        return "CHECK_LOCAL_BROWSER"
    if error_key == "PROXY_CONNECTION_FAILED":
        return "CHECK_PROXY"
    if error_key in {"LOGIN_REQUIRED", "ACCOUNT_VERIFICATION", "TIKTOK_CONTENT_CHECK_SETTING", "ACCOUNT_SETTING_CHECK"}:
        return "HUMAN_ACCOUNT_CHECK"
    if error_key == "FACEBOOK_PAGE_ACCESS":
        return "CHECK_PAGE_ACCESS"
    if error_key in {"MEDIA_PATH_INVALID", "PLAN_CONFIG_INVALID", "UNSUPPORTED_PLATFORM"}:
        return "FIX_PLAN"
    if error_key == "MEDIA_FORMAT_UNSUPPORTED":
        return "FIX_MEDIA"
    if error_key == "PLATFORM_RATE_LIMIT_OR_RESTRICTION":
        return "PAUSE_ACCOUNT"
    if error_key in {
        "POST_URL_NOT_FOUND",
        "FACEBOOK_FILE_CHOOSER_TIMEOUT",
        "TIKTOK_UPLOAD_NOT_CONFIRMED",
        "FACEBOOK_UPLOAD_NOT_CONFIRMED",
        "UPLOAD_NOT_CONFIRMED",
        "FACEBOOK_MEDIA_PROCESSING_NOT_CONFIRMED",
        "TIKTOK_CAPTION_NOT_FILLED",
        "FACEBOOK_CAPTION_NOT_FILLED",
        "CAPTION_NOT_FILLED",
    }:
        return "RETRY_OR_MANUAL_CHECK"
    return "HUMAN_REVIEW"


def describe_error_action(error_action: str) -> str:
    action_key = (error_action or "").strip().upper()
    if not action_key:
        return ""
    label = ERROR_ACTION_LABELS.get(action_key, "")
    return f"{label} ({action_key})" if label else action_key


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
    classified_error = classify_error(error_type, error_message, entry.platform)
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
            "error_type": classified_error,
            "error_action": recommend_error_action(classified_error, "FAILED"),
            "error_action_label": describe_error_action(recommend_error_action(classified_error, "FAILED")),
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
    classified_error = classify_error(error_type, error_message, str(plan.get("platform", "")))
    result = {
        "status": "FAILED",
        "error_type": classified_error,
        "error_action": recommend_error_action(classified_error, "FAILED"),
        "error_action_label": describe_error_action(recommend_error_action(classified_error, "FAILED")),
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
            result["error_action"] = recommend_error_action(partial_error_type, "PARTIAL")
            result["error_message"] = partial_error_message
        else:
            result["error_action"] = recommend_error_action("", result["status"])
        result["error_action_label"] = describe_error_action(str(result.get("error_action") or ""))
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


def _run_single_task_worker(task_args: argparse.Namespace, result_conn: Any) -> None:
    try:
        debug_sleep_seconds = int(getattr(task_args, "debug_task_sleep_seconds", 0) or 0)
        if debug_sleep_seconds > 0:
            time.sleep(debug_sleep_seconds)
        configure_utf8_stdio()
        payload = run_single(task_args)
        result_conn.send({"ok": True, "payload": payload})
    except BaseException as exc:
        result_conn.send(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
    finally:
        try:
            result_conn.close()
        except Exception:
            pass


def run_single_task_isolated(
    task_args: argparse.Namespace,
    timeout_seconds: int,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise BitBrowserError("task timeout must be positive for isolated execution.")

    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_run_single_task_worker,
        args=(task_args, child_conn),
    )
    process.start()
    child_conn.close()
    try:
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(10)
            raise TaskTimeoutError(getattr(task_args, "publish_id", "(unknown)"), timeout_seconds)
        if not parent_conn.poll():
            exit_code = process.exitcode
            if exit_code not in (0, None):
                raise BitBrowserError(
                    f"Child task exited with code {exit_code} before returning a payload."
                )
            raise BitBrowserError("Child task finished without returning a payload.")
        result = parent_conn.recv()
    finally:
        try:
            parent_conn.close()
        except Exception:
            pass

    if not isinstance(result, dict):
        raise BitBrowserError("Child task returned an invalid payload.")
    if result.get("ok"):
        payload = result.get("payload")
        if isinstance(payload, dict):
            return payload
        raise BitBrowserError("Child task returned a non-dict payload.")
    raise ChildTaskError(
        str(result.get("error_type") or "ChildTaskError"),
        str(result.get("error_message") or ""),
    )


def resolve_profile_id_for_timeout_cleanup(
    task_args: argparse.Namespace,
    media_path: Path,
    plan_dir: Path,
) -> str:
    if getattr(task_args, "profile_id", None):
        return str(task_args.profile_id)
    try:
        account_ledger_path = resolve_account_ledger_for_task(
            media_path,
            getattr(task_args, "account_ledger", None),
            plan_dir,
        )
        if account_ledger_path is None:
            return ""
        account_entry = select_account_entry(
            load_account_ledger(account_ledger_path),
            task_args.platform,
            profile_id=getattr(task_args, "profile_id", None),
            account_key=getattr(task_args, "account_key", None),
        )
        return account_entry.profile_id if account_entry else ""
    except Exception:
        return ""


def close_profile_after_timeout(args: argparse.Namespace, profile_id: str) -> None:
    if not profile_id:
        return
    try:
        bit = BitBrowserClient(args.bit_api)
        bit.close_profile(profile_id)
        print(f"Timeout cleanup: closed BitBrowser profile {profile_id}")
    except Exception as exc:
        print(f"Timeout cleanup failed for profile {profile_id}: {exc}", file=sys.stderr)


def run_plan(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan_csv).expanduser().resolve()
    task_timeout_seconds = max(0, int(getattr(args, "task_timeout_seconds", 0) or 0))
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
        cleanup_profile_id = resolve_profile_id_for_timeout_cleanup(
            task_args,
            media_path,
            plan_path.parent,
        )
        if cleanup_profile_id and not task_args.profile_id:
            task_args.profile_id = cleanup_profile_id
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
            if task_timeout_seconds > 0:
                payload = run_single_task_isolated(task_args, task_timeout_seconds)
            else:
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
        except TaskTimeoutError as exc:
            print(f"ERROR {entry.publish_id}: {exc}", file=sys.stderr)
            exit_code = 1
            append_plan_failure(
                args,
                plan_path,
                entry,
                "TASK_TIMEOUT",
                str(exc),
                task_started_at=task_started_at,
                media_path=str(media_path),
            )
            close_profile_after_timeout(args, cleanup_profile_id or task_args.profile_id or "")
            if not args.continue_on_error:
                raise
        except ChildTaskError as exc:
            print(f"ERROR {entry.publish_id}: {exc}", file=sys.stderr)
            exit_code = 1
            if not args.continue_on_error:
                raise
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
            if task_timeout_seconds > 0:
                append_plan_failure(
                    args,
                    plan_path,
                    entry,
                    type(exc).__name__,
                    str(exc),
                    task_started_at=task_started_at,
                    media_path=str(media_path),
                )
            elif not getattr(task_args, "_failure_logged_by_single", False):
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
    if args.detect_post_url:
        return detect_post_url_for_plan(args)
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
    plan_entry = find_publish_plan_entry(plan_path, args.backfill_publish_id)
    platform = normalize_platform_name(args.platform or plan_entry.platform)
    checked_at = datetime.now().isoformat(timespec="seconds")
    platform_post_id = clean_text(args.platform_post_id)
    if status == "PUBLISHED_MANUAL" and not platform_post_id and args.post_url:
        platform_post_id = extract_platform_post_id(args.post_url, platform)
    updates = {
        "status": status,
        "last_result_status": status,
        "last_result_at": checked_at,
        "error_action": recommend_error_action("", status),
        "error_action_label": describe_error_action(recommend_error_action("", status)),
        "post_url": args.post_url or "",
        "platform_post_id": platform_post_id if status == "PUBLISHED_MANUAL" else "",
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
            "error_action": updates["error_action"],
            "error_action_label": updates["error_action_label"],
            "post_url": args.post_url or "",
            "platform_post_id": platform_post_id if status == "PUBLISHED_MANUAL" else "",
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


def detect_post_url_for_plan(args: argparse.Namespace) -> int:
    if not args.plan_csv:
        raise SystemExit("--plan-csv is required when using --detect-post-url.")
    if not args.backfill_publish_id:
        raise SystemExit("--backfill-publish-id is required when using --detect-post-url.")

    plan_path = Path(args.plan_csv).expanduser().resolve()
    plan_entry = find_publish_plan_entry(plan_path, args.backfill_publish_id)
    platform = normalize_platform_name(args.platform or plan_entry.platform)
    if platform not in SUPPORTED_PLATFORMS:
        raise SystemExit(f"Unsupported platform for detection: {platform}")

    profile_id = args.profile_id or plan_entry.browser_profile_id
    account_entry: AccountLedgerEntry | None = None
    if not profile_id:
        ledger_path: Path | None = None
        if args.account_ledger:
            ledger_path = Path(args.account_ledger).expanduser().resolve()
        else:
            maybe_media_path = resolve_path_maybe_relative(plan_entry.media_path, plan_path.parent)
            ledger_path = resolve_account_ledger_for_task(maybe_media_path, None, plan_path.parent)
        if ledger_path is not None and ledger_path.is_file():
            account_entries = load_account_ledger(ledger_path)
            account_entry = select_account_entry(
                account_entries,
                platform,
                profile_id=None,
                account_key=plan_entry.account_key or args.account_key,
            )
            if account_entry is not None:
                profile_id = account_entry.profile_id

    if not profile_id:
        raise SystemExit(
            "profile-id is required unless it can be loaded from the plan row or account ledger."
        )

    bit = BitBrowserClient(args.bit_api)
    health = bit.health()
    opened = bit.open_profile(profile_id)
    pw = None
    browser = None
    result: dict[str, Any]
    try:
        pw, browser, context = connect_browser_context(opened.cdp_url)
        result = detect_post_url_in_context(context, platform)
        result["detection_status"] = "POST_URL_DETECTED" if result.get("detected") else "POST_URL_NOT_FOUND"
        result["status"] = plan_entry.status or "PREPARED"
        if result.get("detected") and args.detect_write_back:
            result["status"] = "PUBLISHED_MANUAL"
        if result.get("detected"):
            result["error_action"] = recommend_error_action("", "PUBLISHED_MANUAL")
        else:
            result["error_type"] = "POST_URL_NOT_FOUND"
            result["error_action"] = recommend_error_action("POST_URL_NOT_FOUND", result["status"])
            result["error_message"] = "No public post URL was found in the current BitBrowser tabs."
        result["error_action_label"] = describe_error_action(str(result.get("error_action") or ""))
        payload = {
            "plan": {
                "started_at": result["checked_at"],
                "publish_id": plan_entry.publish_id,
                "client_id": plan_entry.client_id,
                "product_id": plan_entry.product_id,
                "platform": platform,
                "content_type": plan_entry.content_type,
                "profile_id": profile_id,
                "account_key": plan_entry.account_key,
                "account_platform": account_entry.platform if account_entry else "",
                "profile_name": account_entry.profile_name if account_entry else "",
                "media_path": plan_entry.media_path,
                "plan_csv": str(plan_path),
                "plan_row_status": plan_entry.status,
            },
            "bitbrowser": {
                "health": health,
                "opened_profile": {
                    "profile_id": opened.profile_id,
                    "cdp_source": opened.cdp_source,
                },
                "tab_trace": {"before_detection": snapshot_tabs(context)},
            },
            "result": result,
        }
        print(json.dumps(payload["result"], ensure_ascii=False, indent=2))

        if result.get("detected") and args.detect_write_back:
            checked_at = result["checked_at"]
            updates = {
                "status": "PUBLISHED_MANUAL",
                "last_result_status": "PUBLISHED_MANUAL",
                "last_result_at": checked_at,
                "error_action": recommend_error_action("", "PUBLISHED_MANUAL"),
                "error_action_label": describe_error_action(recommend_error_action("", "PUBLISHED_MANUAL")),
                "post_url": result.get("post_url", ""),
                "platform_post_id": result.get("platform_post_id", ""),
                "published_at": result.get("published_at", checked_at),
                "manual_operator": args.manual_operator or "",
                "manual_checked_at": checked_at,
                "manual_note": args.manual_note
                or "自动识别发布后帖子链接并回填。",
            }
            updated = update_publish_plan_row(plan_path, plan_entry.publish_id, updates)
            print("Detected post backfilled:", json.dumps(updated, ensure_ascii=False))

        if args.log_json:
            write_json_log(Path(args.log_json).expanduser().resolve(), payload)
            print(f"JSON log written: {Path(args.log_json).expanduser().resolve()}")
        if args.log_jsonl:
            append_jsonl_log(Path(args.log_jsonl).expanduser().resolve(), payload)
            print(f"JSONL log appended: {Path(args.log_jsonl).expanduser().resolve()}")
        if not result.get("detected") and args.detect_write_back:
            raise SystemExit("No post URL detected in the current BitBrowser tabs.")
        return 0
    finally:
        if pw is not None:
            pw.stop()


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
        "--task-timeout-seconds",
        type=int,
        default=0,
        help=(
            "Hard timeout for each plan row. When greater than 0, each row runs in an isolated "
            "child process and will be killed if it exceeds this many seconds."
        ),
    )
    parser.add_argument(
        "--debug-task-sleep-seconds",
        type=int,
        default=0,
        help=argparse.SUPPRESS,
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
        "--detect-post-url",
        action="store_true",
        help="Scan the current BitBrowser tabs for a published post URL/post id without clicking publish.",
    )
    parser.add_argument(
        "--detect-write-back",
        action="store_true",
        help="With --detect-post-url, write the detected post URL back to the plan as PUBLISHED_MANUAL.",
    )
    parser.add_argument(
        "--backfill-status",
        choices=MANUAL_BACKFILL_STATUSES,
        default="PUBLISHED_MANUAL",
        help="Manual backfill status. Defaults to PUBLISHED_MANUAL.",
    )
    parser.add_argument("--post-url", help="Published post URL for manual backfill.")
    parser.add_argument("--platform-post-id", help="Platform post ID for manual backfill or detection write-back.")
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
