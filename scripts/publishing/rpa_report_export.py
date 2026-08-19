"""Export RPA publish summaries into customer-reporting seed CSVs.

The RPA publisher writes operational data first. This script turns that data
into a cleaner bridge format for the future customer reporting portal: one
detail file for content-level rows and one overview file grouped by
client/product/platform/content type.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_SUMMARY = "publish_summary.csv"
DEFAULT_DETAIL = "customer_report_seed.csv"
DEFAULT_OVERVIEW = "customer_report_overview.csv"

DETAIL_FIELDS = [
    "report_snapshot_at",
    "client_id",
    "product_id",
    "platform",
    "content_type",
    "publish_id",
    "status",
    "status_group",
    "is_published",
    "needs_post_url",
    "metrics_status",
    "lead_status",
    "post_url",
    "platform_post_id",
    "published_at",
    "account_key",
    "profile_name",
    "profile_id",
    "media_path",
    "title",
    "tracking_url",
    "attribution_token",
    "scheduled_at",
    "screenshot",
    "duration_seconds",
    "started_at",
    "finished_at",
    "manual_operator",
    "manual_checked_at",
    "manual_note",
    "error_type",
    "error_message",
    "views",
    "impressions",
    "likes",
    "comments",
    "shares",
    "saves",
    "profile_visits",
    "link_clicks",
    "raw_inquiries",
    "valid_inquiries",
    "quote_count",
    "deal_count",
    "deal_amount",
    "data_source",
    "report_note",
]

OVERVIEW_FIELDS = [
    "report_snapshot_at",
    "client_id",
    "product_id",
    "platform",
    "content_type",
    "total_tasks",
    "published_count",
    "prepared_count",
    "failed_count",
    "rejected_count",
    "pending_count",
    "post_url_count",
    "missing_post_url_count",
    "metrics_pending_count",
    "lead_pending_count",
    "publish_success_rate",
    "latest_published_at",
    "latest_activity_at",
    "accounts",
    "data_source",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"summary CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [{k: clean_text(v) for k, v in row.items()} for row in csv.DictReader(fh)]


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fieldnames} for row in rows])


def status_group(status: str) -> str:
    key = status.strip().upper()
    if key == "PUBLISHED_MANUAL":
        return "PUBLISHED"
    if key == "PREPARED":
        return "DRAFT_PREPARED"
    if key in {"FAILED", "PARTIAL"}:
        return "NEEDS_OPERATOR"
    if key in {"REJECTED_MANUAL", "SKIPPED"}:
        return "NOT_PUBLISHED"
    if key in {"READY", "RUNNING", "PLANNED"}:
        return "PENDING"
    return "UNKNOWN" if key else "UNKNOWN"


def is_published(row: dict[str, str]) -> bool:
    return status_group(row.get("status", "")) == "PUBLISHED" or bool(row.get("post_url", ""))


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00%"
    return f"{(numerator / denominator) * 100:.2f}%"


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def latest_time(*values: str) -> str:
    latest_value = ""
    latest_dt: datetime | None = None
    for value in values:
        current = clean_text(value)
        current_dt = parse_time(current)
        if current_dt is not None:
            if latest_dt is None or current_dt >= latest_dt:
                latest_dt = current_dt
                latest_value = current
        elif not latest_value and current:
            latest_value = current
    return latest_value


def build_detail_rows(summary_rows: list[dict[str, str]], snapshot_at: str) -> list[dict[str, str]]:
    detail_rows: list[dict[str, str]] = []
    for row in summary_rows:
        published = is_published(row)
        post_url = row.get("post_url", "")
        group = status_group(row.get("status", ""))
        report_note = ""
        if published and not post_url:
            report_note = "已标记发布，但缺少公开帖子链接，需要人工补齐。"
        elif group == "NEEDS_OPERATOR":
            report_note = "发布准备失败或部分成功，需要运营判断重试、换号或人工处理。"
        elif group == "DRAFT_PREPARED":
            report_note = "草稿已准备，等待人工检查并点击发布。"

        detail_rows.append(
            {
                "report_snapshot_at": snapshot_at,
                "client_id": row.get("client_id", ""),
                "product_id": row.get("product_id", ""),
                "platform": row.get("platform", ""),
                "content_type": row.get("content_type", ""),
                "publish_id": row.get("publish_id", ""),
                "status": row.get("status", ""),
                "status_group": group,
                "is_published": "true" if published else "false",
                "needs_post_url": "true" if published and not post_url else "false",
                "metrics_status": "PENDING_METRICS" if published else "NOT_READY",
                "lead_status": "PENDING_LEADS" if published else "NOT_READY",
                "post_url": post_url,
                "platform_post_id": row.get("platform_post_id", ""),
                "published_at": row.get("published_at", ""),
                "account_key": row.get("account_key", ""),
                "profile_name": row.get("profile_name", ""),
                "profile_id": row.get("profile_id", ""),
                "media_path": row.get("media_path", ""),
                "title": row.get("title", ""),
                "tracking_url": row.get("tracking_url", ""),
                "attribution_token": row.get("attribution_token", ""),
                "scheduled_at": row.get("scheduled_at", ""),
                "screenshot": row.get("screenshot", ""),
                "duration_seconds": row.get("duration_seconds", ""),
                "started_at": row.get("started_at", ""),
                "finished_at": row.get("finished_at", ""),
                "manual_operator": row.get("manual_operator", ""),
                "manual_checked_at": row.get("manual_checked_at", ""),
                "manual_note": row.get("manual_note", ""),
                "error_type": row.get("error_type", ""),
                "error_message": row.get("error_message", ""),
                "data_source": "rpa_publish_summary",
                "report_note": report_note,
            }
        )
    return detail_rows


def build_overview_rows(detail_rows: list[dict[str, str]], snapshot_at: str) -> list[dict[str, str]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in detail_rows:
        key = (
            row.get("client_id", ""),
            row.get("product_id", ""),
            row.get("platform", ""),
            row.get("content_type", ""),
        )
        groups[key].append(row)

    overview_rows: list[dict[str, str]] = []
    for key, rows in groups.items():
        client_id, product_id, platform, content_type = key
        counts = Counter(row.get("status_group", "UNKNOWN") for row in rows)
        published_count = counts.get("PUBLISHED", 0)
        post_url_count = sum(1 for row in rows if row.get("post_url"))
        metrics_pending_count = sum(1 for row in rows if row.get("metrics_status") == "PENDING_METRICS")
        lead_pending_count = sum(1 for row in rows if row.get("lead_status") == "PENDING_LEADS")
        latest_published_at = latest_time(*(row.get("published_at", "") for row in rows))
        latest_activity_at = latest_time(
            *(row.get("finished_at", "") or row.get("published_at", "") or row.get("scheduled_at", "") for row in rows)
        )
        accounts = sorted({row.get("account_key", "") for row in rows if row.get("account_key", "")})
        overview_rows.append(
            {
                "report_snapshot_at": snapshot_at,
                "client_id": client_id,
                "product_id": product_id,
                "platform": platform,
                "content_type": content_type,
                "total_tasks": str(len(rows)),
                "published_count": str(published_count),
                "prepared_count": str(counts.get("DRAFT_PREPARED", 0)),
                "failed_count": str(counts.get("NEEDS_OPERATOR", 0)),
                "rejected_count": str(counts.get("NOT_PUBLISHED", 0)),
                "pending_count": str(counts.get("PENDING", 0) + counts.get("UNKNOWN", 0)),
                "post_url_count": str(post_url_count),
                "missing_post_url_count": str(max(published_count - post_url_count, 0)),
                "metrics_pending_count": str(metrics_pending_count),
                "lead_pending_count": str(lead_pending_count),
                "publish_success_rate": pct(published_count, len(rows)),
                "latest_published_at": latest_published_at,
                "latest_activity_at": latest_activity_at,
                "accounts": ";".join(accounts),
                "data_source": "rpa_publish_summary",
            }
        )

    return sorted(
        overview_rows,
        key=lambda row: (
            row.get("client_id", ""),
            row.get("product_id", ""),
            row.get("platform", ""),
            row.get("content_type", ""),
        ),
    )


def export_customer_report(
    summary_csv: Path,
    detail_csv: Path,
    overview_csv: Path,
    snapshot_at: str | None = None,
) -> dict[str, Any]:
    snapshot = snapshot_at or datetime.now().isoformat(timespec="seconds")
    summary_rows = read_csv_rows(summary_csv)
    detail_rows = build_detail_rows(summary_rows, snapshot)
    overview_rows = build_overview_rows(detail_rows, snapshot)
    write_csv_rows(detail_csv, DETAIL_FIELDS, detail_rows)
    write_csv_rows(overview_csv, OVERVIEW_FIELDS, overview_rows)
    return {
        "summary_csv": str(summary_csv),
        "detail_csv": str(detail_csv),
        "overview_csv": str(overview_csv),
        "detail_rows": len(detail_rows),
        "overview_rows": len(overview_rows),
        "snapshot_at": snapshot,
    }


def default_output_path(summary_csv: Path, filename: str) -> Path:
    return summary_csv.parent / filename


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export publish_summary.csv into customer reporting seed CSVs"
    )
    parser.add_argument("--summary-csv", default=DEFAULT_SUMMARY, help="Input publish_summary.csv path")
    parser.add_argument("--detail-csv", help=f"Output detail CSV. Default: {DEFAULT_DETAIL} beside summary")
    parser.add_argument("--overview-csv", help=f"Output overview CSV. Default: {DEFAULT_OVERVIEW} beside summary")
    parser.add_argument("--snapshot-at", help="Optional report snapshot timestamp")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary_csv = Path(args.summary_csv).expanduser().resolve()
    detail_csv = Path(args.detail_csv).expanduser().resolve() if args.detail_csv else default_output_path(summary_csv, DEFAULT_DETAIL)
    overview_csv = (
        Path(args.overview_csv).expanduser().resolve()
        if args.overview_csv
        else default_output_path(summary_csv, DEFAULT_OVERVIEW)
    )
    result = export_customer_report(summary_csv, detail_csv, overview_csv, args.snapshot_at)
    print(f"Customer report detail written: {result['detail_csv']}")
    print(f"Customer report overview written: {result['overview_csv']}")
    print(f"Rows: detail={result['detail_rows']} overview={result['overview_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
