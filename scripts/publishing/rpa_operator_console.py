"""
Generate a local RPA operator console HTML page from publish CSV/JSONL files.

The console is static on purpose: it reads local files, writes one HTML file, and
does not require a web server or the main DopaMatrix application.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from bitbrowser_rpa_example import describe_error_action, recommend_error_action
from rpa_csv import read_csv_rows as read_validated_csv_rows


DEFAULT_PLAN = "publish_plan.csv"
DEFAULT_JSONL = "publish_logs.jsonl"
DEFAULT_SUMMARY = "publish_summary.csv"
DEFAULT_OUTPUT = "rpa_operator_console.html"

FIELDS = [
    "publish_id",
    "platform",
    "status",
    "content_type",
    "facebook_content_mode",
    "composer_url",
    "account_key",
    "profile_name",
    "client_id",
    "product_id",
    "profile_id",
    "media_path",
    "title",
    "uploaded",
    "caption_filled",
    "media_processing_required",
    "media_processing_confirmed",
    "media_processing_signal",
    "processing_wait_seconds",
    "duration_seconds",
    "error_type",
    "error_action",
    "error_action_label",
    "error_message",
    "candidate_count",
    "candidate_sources",
    "scanned_tab_count",
    "scanner_error_count",
    "scanner_errors",
    "screenshot",
    "post_url",
    "platform_post_id",
    "published_at",
    "started_at",
    "finished_at",
    "manual_operator",
    "manual_checked_at",
    "manual_note",
    "tracking_url",
    "attribution_token",
    "plan_csv",
    "url",
    "checkpoint",
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    return read_validated_csv_rows(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(body, dict):
                rows.append(body)
    return rows


def first_nonempty(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key, "")
        if value:
            return value
    return ""


def normalize_plan_row(row: dict[str, str], plan_csv: Path) -> dict[str, str]:
    return {
        "publish_id": first_nonempty(row, "publish_id", "发布ID", "id"),
        "platform": first_nonempty(row, "platform", "平台"),
        "content_type": first_nonempty(row, "content_type", "内容类型"),
        "facebook_content_mode": first_nonempty(row, "facebook_content_mode", "fb_content_mode", "Facebook内容模式", "FB内容模式", "内容模式"),
        "composer_url": first_nonempty(row, "composer_url", "facebook_composer_url", "target_url", "发布入口", "入口URL"),
        "status": first_nonempty(row, "status", "状态"),
        "account_key": first_nonempty(row, "account_key", "账号键", "account_code"),
        "profile_name": first_nonempty(row, "profile_name", "窗口名称"),
        "profile_id": first_nonempty(row, "browser_profile_id", "profile_id", "窗口ID", "browser_id"),
        "client_id": first_nonempty(row, "client_id", "客户ID"),
        "product_id": first_nonempty(row, "product_id", "产品ID", "sku"),
        "media_path": first_nonempty(row, "media_path", "素材路径", "media", "path"),
        "title": first_nonempty(row, "title", "标题", "社交平台标题"),
        "caption": first_nonempty(row, "caption", "文案", "description", "情绪化描述"),
        "hashtags": first_nonempty(row, "hashtags", "标签", "黄金标签"),
        "tracking_url": first_nonempty(row, "tracking_url", "tracking_link", "追踪短链接"),
        "attribution_token": first_nonempty(row, "attribution_token", "归因token"),
        "screenshot": first_nonempty(row, "result_screenshot", "screenshot", "结果截图"),
        "error_type": first_nonempty(row, "error_type", "错误类型"),
        "error_action": first_nonempty(row, "error_action", "处理建议", "处置建议"),
        "error_action_label": first_nonempty(row, "error_action_label", "处理建议说明", "处置建议说明"),
        "error_message": first_nonempty(row, "error_message", "错误信息"),
        "post_url": first_nonempty(row, "post_url", "帖子链接", "发布链接"),
        "platform_post_id": first_nonempty(row, "platform_post_id", "平台post_id", "平台帖子ID", "post_id"),
        "published_at": first_nonempty(row, "published_at", "发布时间"),
        "manual_operator": first_nonempty(row, "manual_operator", "人工操作人"),
        "manual_checked_at": first_nonempty(row, "manual_checked_at", "人工确认时间"),
        "manual_note": first_nonempty(row, "manual_note", "人工备注"),
        "plan_csv": str(plan_csv),
    }


def normalize_summary_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {field: row.get(field, "").strip() for field in FIELDS}
    normalized["profile_name"] = row.get("profile_name", "").strip()
    normalized["profile_id"] = row.get("profile_id", "").strip()
    if not normalized.get("error_action"):
        normalized["error_action"] = recommend_error_action(normalized.get("error_type", ""), normalized.get("status", ""))
    if not normalized.get("error_action_label"):
        normalized["error_action_label"] = describe_error_action(normalized.get("error_action", ""))
    return normalized


def stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def jsonl_value(payload: dict[str, Any], key: str) -> str:
    plan = payload.get("plan") or {}
    result = payload.get("result") or {}
    if not isinstance(plan, dict):
        plan = {}
    if not isinstance(result, dict):
        result = {}

    if key == "started_at":
        value = plan.get("started_at", "")
    elif key in {
        "finished_at",
        "uploaded",
        "caption_filled",
        "media_processing_required",
        "media_processing_confirmed",
        "media_processing_signal",
        "processing_wait_seconds",
        "url",
        "checkpoint",
    }:
        value = result.get(key, "")
    else:
        value = result.get(key, "")
        if value in (None, ""):
            value = plan.get(key, "")
    if key == "candidate_sources" and isinstance(value, (list, tuple, set)):
        value = " | ".join(str(item) for item in value if str(item).strip())
    elif key == "scanner_errors" and isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if not isinstance(item, dict):
                text = str(item).strip()
                if text:
                    parts.append(text)
                continue
            source = str(item.get("source", "")).strip()
            tab_url = str(item.get("tab_url", "")).strip()
            text = str(item.get("text", "")).strip()
            chunk = " ".join(part for part in [source, tab_url, text] if part)
            if chunk:
                parts.append(chunk)
        value = " | ".join(parts)
    return stringify(value).strip()


def normalize_jsonl_row(payload: dict[str, Any]) -> dict[str, str]:
    row = {field: jsonl_value(payload, field) for field in FIELDS}
    if not row["publish_id"]:
        row["publish_id"] = "(manual-entry)"
    if not row.get("error_action"):
        row["error_action"] = recommend_error_action(row.get("error_type", ""), row.get("status", ""))
    if not row.get("error_action_label"):
        row["error_action_label"] = describe_error_action(row.get("error_action", ""))
    return row


def latest_jsonl_rows(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for record in records:
        row = normalize_jsonl_row(record)
        publish_id = row.get("publish_id", "")
        if not publish_id:
            continue
        current = latest.get(publish_id)
        if current is None or row_sort_time(row) >= row_sort_time(current):
            latest[publish_id] = row
    return list(latest.values())


def row_sort_time(row: dict[str, str]) -> str:
    return row.get("finished_at") or row.get("started_at") or ""


def merge_rows(plan_rows: list[dict[str, str]], summary_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for row in plan_rows:
        publish_id = row.get("publish_id", "")
        if publish_id:
            merged[publish_id] = {field: row.get(field, "") for field in FIELDS}

    for row in summary_rows:
        publish_id = row.get("publish_id", "")
        if not publish_id:
            continue
        current = merged.setdefault(publish_id, {field: "" for field in FIELDS})
        for field in FIELDS:
            value = row.get(field, "")
            if value:
                current[field] = value

    for row in merged.values():
        if not row.get("error_action"):
            row["error_action"] = recommend_error_action(row.get("error_type", ""), row.get("status", ""))
        if not row.get("error_action_label"):
            row["error_action_label"] = describe_error_action(row.get("error_action", ""))

    return sorted(merged.values(), key=lambda item: (item.get("platform", ""), item.get("publish_id", "")))


def to_file_uri(path_text: str, base_dir: Path) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    try:
        return path.as_uri()
    except ValueError:
        return ""


def escape(value: str) -> str:
    return html.escape(value or "", quote=True)


def status_class(status: str) -> str:
    key = (status or "UNKNOWN").upper()
    if key in {"PREPARED", "PUBLISHED_MANUAL"}:
        return "ok"
    if key in {"FAILED", "PARTIAL"}:
        return "bad"
    if key in {"REJECTED_MANUAL", "SKIPPED"}:
        return "muted"
    return "wait"


def append_log_arg(command: str, log_jsonl: str) -> str:
    if not log_jsonl:
        return command
    return f'{command} --log-jsonl "{log_jsonl}"'


def build_backfill_command(row: dict[str, str], status: str, log_jsonl: str = "") -> str:
    plan_csv = row.get("plan_csv", "")
    publish_id = row.get("publish_id", "")
    command = (
        "python docs\\scripts\\publishing\\bitbrowser_rpa_example.py "
        f"--plan-csv \"{plan_csv}\" "
        f"--backfill-publish-id {publish_id} "
        f"--backfill-status {status} "
    )
    if status == "PUBLISHED_MANUAL":
        post_url = row.get("post_url", "") or "PASTE_POST_URL_HERE"
        platform_post_id = row.get("platform_post_id", "")
        command += f"--post-url \"{post_url}\" "
        if platform_post_id:
            command += f"--platform-post-id \"{platform_post_id}\" "
        command += "--published-at \"YYYY-MM-DDTHH:MM:SS\" "
    command += (
        "--manual-operator operator "
        "--manual-note \"人工检查后回填\""
    )
    return append_log_arg(command, log_jsonl)


def build_detect_command(row: dict[str, str], log_jsonl: str = "") -> str:
    plan_csv = row.get("plan_csv", "")
    publish_id = row.get("publish_id", "")
    command = (
        "python docs\\scripts\\publishing\\bitbrowser_rpa_example.py "
        f"--plan-csv \"{plan_csv}\" "
        f"--backfill-publish-id {publish_id} "
        "--detect-post-url "
    )
    return append_log_arg(command, log_jsonl)


def build_retry_command(row: dict[str, str], log_jsonl: str = "") -> str:
    plan_csv = row.get("plan_csv", "")
    publish_id = row.get("publish_id", "")
    command = (
        "python docs\\scripts\\publishing\\bitbrowser_rpa_example.py "
        f"--plan-csv \"{plan_csv}\" "
        f"--only-publish-id {publish_id} "
        "--include-status FAILED,PARTIAL,READY "
        "--limit 1 "
        "--write-plan-status "
        "--continue-on-error "
        "--task-timeout-seconds 600 "
        "--content-check-action cancel"
    )
    return append_log_arg(command, log_jsonl)


def render_rows(rows: list[dict[str, str]], plan_dir: Path, log_jsonl: str) -> str:
    cards: list[str] = []
    for row in rows:
        screenshot_uri = to_file_uri(row.get("screenshot", ""), plan_dir)
        screenshot = (
            f'<a href="{escape(screenshot_uri)}" target="_blank"><img src="{escape(screenshot_uri)}" alt="screenshot"></a>'
            if screenshot_uri
            else '<div class="empty-shot">No screenshot</div>'
        )
        publish_cmd = build_backfill_command(row, "PUBLISHED_MANUAL", log_jsonl)
        reject_cmd = build_backfill_command(row, "REJECTED_MANUAL", log_jsonl)
        retry_cmd = build_retry_command(row, log_jsonl)
        status = row.get("status", "")
        duration = row.get("duration_seconds", "")
        duration_text = f"{escape(duration)}s" if duration else ""
        search_text = " ".join(
            row.get(key, "")
            for key in (
                "publish_id",
                "platform",
                "content_type",
                "facebook_content_mode",
                "account_key",
                "profile_id",
                "profile_name",
                "client_id",
                "product_id",
                "title",
                "media_path",
                "tracking_url",
                "composer_url",
                "post_url",
                "platform_post_id",
                "published_at",
                "attribution_token",
                "error_type",
                "error_action",
                "error_action_label",
                "manual_note",
                "candidate_count",
                "candidate_sources",
                "scanned_tab_count",
                "scanner_error_count",
                "scanner_errors",
            )
        ).lower()
        cards.append(
            f"""
            <article class="task" data-status="{escape(status.upper())}" data-platform="{escape(row.get('platform', '').lower())}" data-action="{escape((row.get('error_action') or 'NONE').upper())}" data-search="{escape(search_text)}">
              <div class="shot">{screenshot}</div>
              <div class="task-main">
                <div class="task-head">
                  <span class="badge {status_class(status)}">{escape(status or 'UNKNOWN')}</span>
                  <span class="platform">{escape(row.get('platform', ''))}</span>
                  <span class="duration">{duration_text}</span>
                </div>
                <h2>{escape(row.get('publish_id', ''))}</h2>
                <p class="title">{escape(row.get('title', ''))}</p>
                <div class="meta">
                  <span>账号：{escape(row.get('account_key', ''))}</span>
                  <span>窗口：{escape(row.get('profile_name', ''))}</span>
                  <span>客户：{escape(row.get('client_id', ''))}</span>
                  <span>产品：{escape(row.get('product_id', ''))}</span>
                  <span>内容：{escape(row.get('content_type', ''))}</span>
                  <span>FB模式：{escape(row.get('facebook_content_mode', ''))}</span>
                  <span>上传：{escape(row.get('uploaded', ''))}</span>
                  <span>文案：{escape(row.get('caption_filled', ''))}</span>
                  <span>媒体处理：{escape(row.get('media_processing_confirmed', ''))}</span>
                  <span>处理耗时：{escape(row.get('processing_wait_seconds', ''))}</span>
                </div>
                <div class="paths">
                  <div>入口：{escape(row.get('composer_url', ''))}</div>
                  <div>处理信号：{escape(row.get('media_processing_signal', ''))}</div>
                  <div>短链：{escape(row.get('tracking_url', ''))}</div>
                  <div>帖子：{escape(row.get('post_url', ''))}</div>
                  <div>帖子ID：{escape(row.get('platform_post_id', ''))}</div>
                  <div>发布时间：{escape(row.get('published_at', ''))}</div>
                  <div>素材：{escape(row.get('media_path', ''))}</div>
                  <div>截图：{escape(row.get('screenshot', ''))}</div>
                </div>
                <div class="manual">
                  <div>人工：{escape(row.get('manual_operator', ''))} {escape(row.get('manual_checked_at', ''))}</div>
                  <div>{escape(row.get('manual_note', ''))}</div>
                </div>
                <div class="error">{escape(row.get('error_type', ''))} {escape(row.get('error_action_label') or row.get('error_action', ''))} {escape(row.get('error_message', ''))}</div>
                <div class="diagnostics">
                  <div>候选：{escape(row.get('candidate_count', ''))} / 来源：{escape(row.get('candidate_sources', ''))}</div>
                  <div>扫描页签：{escape(row.get('scanned_tab_count', ''))} / 扫描错误：{escape(row.get('scanner_error_count', ''))}</div>
                  <div>{escape(row.get('scanner_errors', ''))}</div>
                </div>
                <details>
                  <summary>回填命令</summary>
                  <label>已发布</label>
                  <button class="copy-btn" data-copy="{escape(publish_cmd)}">复制已发布回填</button>
                  <textarea readonly>{escape(publish_cmd)}</textarea>
                  <label>识别帖子</label>
                  <button class="copy-btn" data-copy="{escape(build_detect_command(row, log_jsonl))}">复制识别命令</button>
                  <textarea readonly>{escape(build_detect_command(row, log_jsonl))}</textarea>
                  <label>不发布</label>
                  <button class="copy-btn" data-copy="{escape(reject_cmd)}">复制不发布回填</button>
                  <textarea readonly>{escape(reject_cmd)}</textarea>
                  <label>失败/部分成功重试</label>
                  <button class="copy-btn" data-copy="{escape(retry_cmd)}">复制重试命令</button>
                  <textarea readonly>{escape(retry_cmd)}</textarea>
                </details>
              </div>
            </article>
            """
        )
    return "\n".join(cards)


def render_html(rows: list[dict[str, str]], args: argparse.Namespace, source_info: dict[str, str]) -> str:
    counts = Counter((row.get("status") or "UNKNOWN").upper() for row in rows)
    platforms = Counter((row.get("platform") or "unknown").lower() for row in rows)
    actions = Counter((row.get("error_action") or "NONE").upper() for row in rows)
    avg_duration_values = [
        float(row["duration_seconds"])
        for row in rows
        if row.get("duration_seconds", "").replace(".", "", 1).isdigit()
    ]
    avg_duration = round(sum(avg_duration_values) / len(avg_duration_values), 2) if avg_duration_values else 0
    generated_at = datetime.now().isoformat(timespec="seconds")
    log_jsonl = source_info.get("log_jsonl", "")
    body_rows = render_rows(rows, Path(args.plan_csv).expanduser().resolve().parent, log_jsonl)
    statuses = sorted(counts)
    status_buttons = "".join(
        f'<button data-filter-status="{escape(status)}">{escape(status)} ({counts[status]})</button>'
        for status in statuses
    )
    platform_buttons = "".join(
        f'<button data-filter-platform="{escape(platform)}">{escape(platform)} ({platforms[platform]})</button>'
        for platform in sorted(platforms)
    )
    action_buttons = "".join(
        f'<button data-filter-action="{escape(action)}">{escape(action)} ({actions[action]})</button>'
        for action in sorted(actions)
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RPA 发布操作台</title>
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
      --soft: #eef4ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: var(--ink); background: #ffffff; }}
    header {{ padding: 18px 24px 14px; border-bottom: 1px solid var(--line); background: #fff; position: sticky; top: 0; z-index: 2; }}
    h1 {{ margin: 0 0 12px; font-size: 22px; font-weight: 700; }}
    .source {{ display: grid; gap: 4px; color: var(--muted); font-size: 13px; }}
    .stats {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }}
    .stat {{ border: 1px solid var(--line); background: var(--panel); padding: 8px 10px; min-width: 128px; }}
    .stat strong {{ display: block; font-size: 20px; }}
    .toolbar {{ display: grid; gap: 10px; padding: 14px 24px; border-bottom: 1px solid var(--line); }}
    .filter-row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .search {{ width: min(520px, 100%); border: 1px solid var(--line); padding: 9px 10px; font-size: 14px; }}
    button {{ border: 1px solid var(--line); background: #fff; color: var(--ink); padding: 8px 10px; cursor: pointer; }}
    button.active {{ border-color: #246bfd; background: var(--soft); color: #1849a9; }}
    .copy-btn {{ margin: 6px 0; padding: 6px 8px; font-size: 12px; }}
    main {{ padding: 18px 24px 40px; display: grid; gap: 14px; }}
    .task {{ border: 1px solid var(--line); display: grid; grid-template-columns: 260px 1fr; min-height: 190px; background: #fff; }}
    .shot {{ background: #f2f5f7; border-right: 1px solid var(--line); display: flex; align-items: center; justify-content: center; overflow: hidden; }}
    .shot img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
    .empty-shot {{ color: var(--muted); font-size: 13px; }}
    .task-main {{ padding: 14px 16px; min-width: 0; }}
    .task-head {{ display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; }}
    .badge {{ border: 1px solid var(--line); padding: 3px 7px; font-weight: 700; }}
    .badge.ok {{ color: var(--ok); border-color: #9dd8bd; background: #ecfdf3; }}
    .badge.bad {{ color: var(--bad); border-color: #fecdca; background: #fff1f3; }}
    .badge.wait {{ color: var(--wait); border-color: #fedf89; background: #fffaeb; }}
    .badge.muted {{ color: #475467; border-color: #d0d5dd; background: #f2f4f7; }}
    h2 {{ margin: 8px 0 6px; font-size: 18px; }}
    .title {{ margin: 0 0 10px; color: var(--ink); }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px 14px; font-size: 13px; color: var(--muted); margin-bottom: 10px; }}
    .paths, .manual, .error, .diagnostics {{ font-size: 12px; color: var(--muted); display: grid; gap: 4px; overflow-wrap: anywhere; }}
    .error {{ color: var(--bad); margin-top: 6px; }}
    details {{ margin-top: 10px; border-top: 1px solid var(--line); padding-top: 8px; }}
    summary {{ cursor: pointer; color: #1849a9; font-size: 13px; }}
    label {{ display: block; margin-top: 8px; color: var(--muted); font-size: 12px; }}
    textarea {{ width: 100%; min-height: 62px; resize: vertical; font-family: Consolas, monospace; font-size: 12px; border: 1px solid var(--line); padding: 8px; }}
    @media (max-width: 820px) {{
      header, .toolbar, main {{ padding-left: 14px; padding-right: 14px; }}
      .task {{ grid-template-columns: 1fr; }}
      .shot {{ height: 220px; border-right: 0; border-bottom: 1px solid var(--line); }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>RPA 发布操作台</h1>
    <div class="source">
      <span>生成时间：{escape(generated_at)}</span>
      <span>计划表：{escape(source_info.get("plan_csv", ""))}</span>
      <span>日志：{escape(source_info.get("log_jsonl", ""))}</span>
      <span>汇总：{escape(source_info.get("summary_csv", ""))}</span>
    </div>
    <div class="stats">
      <div class="stat"><strong>{len(rows)}</strong>任务数</div>
      <div class="stat"><strong>{platforms.get("tiktok", 0)}</strong>TikTok</div>
      <div class="stat"><strong>{platforms.get("facebook", 0)}</strong>Facebook</div>
      <div class="stat"><strong>{avg_duration}</strong>平均秒数</div>
    </div>
  </header>
  <nav class="toolbar">
    <div class="filter-row">
      <input class="search" id="search" placeholder="搜索 publish_id / 账号 / 客户 / 产品 / 素材 / 错误" autocomplete="off">
    </div>
    <div class="filter-row">
      <button class="active" data-filter-status="ALL">全部状态 ({len(rows)})</button>
      {status_buttons}
    </div>
    <div class="filter-row">
      <button class="active" data-filter-platform="ALL">全部平台 ({len(rows)})</button>
      {platform_buttons}
    </div>
    <div class="filter-row">
      <button class="active" data-filter-action="ALL">全部建议 ({len(rows)})</button>
      {action_buttons}
    </div>
  </nav>
  <main>{body_rows}</main>
  <script>
    const statusButtons = document.querySelectorAll('button[data-filter-status]');
    const platformButtons = document.querySelectorAll('button[data-filter-platform]');
    const actionButtons = document.querySelectorAll('button[data-filter-action]');
    const tasks = document.querySelectorAll('.task');
    const search = document.querySelector('#search');
    let activeStatus = 'ALL';
    let activePlatform = 'ALL';
    let activeAction = 'ALL';

    function applyFilters() {{
      const term = (search.value || '').trim().toLowerCase();
      tasks.forEach((task) => {{
        const statusMatch = activeStatus === 'ALL' || task.dataset.status === activeStatus;
        const platformMatch = activePlatform === 'ALL' || task.dataset.platform === activePlatform;
        const actionMatch = activeAction === 'ALL' || task.dataset.action === activeAction;
        const searchMatch = !term || (task.dataset.search || '').includes(term);
        task.style.display = statusMatch && platformMatch && actionMatch && searchMatch ? '' : 'none';
      }});
    }}

    function activate(buttons, button) {{
      buttons.forEach((item) => item.classList.remove('active'));
      button.classList.add('active');
    }}

    statusButtons.forEach((button) => {{
      button.addEventListener('click', () => {{
        activate(statusButtons, button);
        activeStatus = button.dataset.filterStatus;
        applyFilters();
      }});
    }});
    platformButtons.forEach((button) => {{
      button.addEventListener('click', () => {{
        activate(platformButtons, button);
        activePlatform = button.dataset.filterPlatform;
        applyFilters();
      }});
    }});
    actionButtons.forEach((button) => {{
      button.addEventListener('click', () => {{
        activate(actionButtons, button);
        activeAction = button.dataset.filterAction;
        applyFilters();
      }});
    }});
    search.addEventListener('input', applyFilters);

    async function copyText(text) {{
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        await navigator.clipboard.writeText(text);
        return;
      }}
      const helper = document.createElement('textarea');
      helper.value = text;
      helper.style.position = 'fixed';
      helper.style.left = '-9999px';
      document.body.appendChild(helper);
      helper.focus();
      helper.select();
      document.execCommand('copy');
      helper.remove();
    }}

    document.querySelectorAll('.copy-btn').forEach((button) => {{
      button.addEventListener('click', async () => {{
        const label = button.textContent;
        try {{
          await copyText(button.dataset.copy || '');
          button.textContent = '已复制';
          setTimeout(() => {{ button.textContent = label; }}, 1200);
        }} catch (error) {{
          button.textContent = '复制失败';
          setTimeout(() => {{ button.textContent = label; }}, 1600);
        }}
      }});
    }});
  </script>
</body>
</html>
"""


def generate_console(args: argparse.Namespace) -> Path:
    plan_path = Path(args.plan_csv).expanduser().resolve()
    summary_path = Path(args.summary_csv).expanduser().resolve() if args.summary_csv else plan_path.parent / DEFAULT_SUMMARY
    log_path = Path(args.log_jsonl).expanduser().resolve() if args.log_jsonl else plan_path.parent / DEFAULT_JSONL
    output_path = Path(args.output_html).expanduser().resolve() if args.output_html else plan_path.parent / DEFAULT_OUTPUT

    plan_rows = [normalize_plan_row(row, plan_path) for row in read_csv_rows(plan_path)]
    summary_rows = [normalize_summary_row(row) for row in read_csv_rows(summary_path)]
    if not summary_rows:
        summary_rows = latest_jsonl_rows(read_jsonl(log_path))
    rows = merge_rows(plan_rows, summary_rows)
    if not rows:
        raise SystemExit(f"No rows found for console: {plan_path}")

    source_info = {
        "plan_csv": str(plan_path),
        "log_jsonl": str(log_path) if log_path.is_file() else "",
        "summary_csv": str(summary_path) if summary_path.is_file() else "",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(rows, args, source_info), encoding="utf-8")
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a local RPA operator console HTML")
    parser.add_argument("--plan-csv", required=True, help="publish_plan.csv path")
    parser.add_argument("--log-jsonl", help="publish_logs.jsonl path")
    parser.add_argument("--summary-csv", help="publish_summary.csv path")
    parser.add_argument("--output-html", help="Output HTML path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = generate_console(args)
    print(f"RPA operator console written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
