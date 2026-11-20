"""Merge saved delivery copy and new media into an existing publish plan."""

from __future__ import annotations

import argparse
import csv
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from bitbrowser_rpa_example import (
    DEFAULT_DELIVERY_CSV_FILENAME,
    DEFAULT_WORK_DIRNAME,
    IMAGE_EXTENSIONS,
    PLAN_STATUS_COLUMNS,
    PUBLISH_PLAN_FIELDS,
    SUMMARY_PLAN_COLUMNS,
    VIDEO_EXTENSIONS,
    BitBrowserError,
    build_generated_plan_row,
    choose_round_robin_account,
    load_account_ledger,
    load_delivery_records,
    load_publish_plan,
    normalize_platform_name,
    resolve_path_maybe_relative,
    scan_media_files,
    usable_accounts_by_platform,
)
from rpa_csv import read_csv_table


def sync_delivery_plan(plan_path: Path, ledger_path: Path) -> dict:
    package_root = plan_path.parent.parent if plan_path.parent.name == DEFAULT_WORK_DIRNAME else plan_path.parent
    source = package_root / DEFAULT_DELIVERY_CSV_FILENAME
    result = {"added": 0, "updated": 0, "warnings": [], "delivery_csv": str(source)}
    warnings = result["warnings"]
    if not source.is_file():
        warnings.append(f"未找到投放文案表，仅刷新原有计划：{source}")
        return result

    records = load_delivery_records(source)
    counts = Counter(record.video_filename for record in records)
    for filename, count in counts.items():
        if not filename or count != 1:
            raise BitBrowserError(f"文案表的素材文件名为空或重复：{filename or '空文件名'}。请修正后刷新。")
    record_index = {record.video_filename: record for record in records}
    entries = load_publish_plan(plan_path)
    ids = Counter(entry.publish_id for entry in entries)
    if any(count != 1 for count in ids.values()):
        raise BitBrowserError("计划表任务 ID 重复，请先修正后刷新。")

    media_index = defaultdict(list)
    for media in scan_media_files(package_root, VIDEO_EXTENSIONS | IMAGE_EXTENSIONS):
        media_index[media.name].append(media)
    routes = defaultdict(lambda: defaultdict(list))
    existing = set()
    account_counters = Counter()
    for entry in entries:
        media = resolve_path_maybe_relative(entry.media_path, plan_path.parent)
        kind = "video" if media.suffix.lower() in VIDEO_EXTENSIONS else "image" if media.suffix.lower() in IMAGE_EXTENSIONS else entry.content_type
        platform = normalize_platform_name(entry.platform)
        if platform in {"tiktok", "facebook"} and kind in {"video", "image"}:
            routes[kind][platform].append(entry)
            existing.add((platform, media))
            account_counters[platform] += 1

    fieldnames, rows = read_csv_table(plan_path)

    def column_for(key: str) -> str:
        canonical = "profile_id" if key == "browser_profile_id" else key
        aliases = (key, *PLAN_STATUS_COLUMNS.get(canonical, ()), *SUMMARY_PLAN_COLUMNS.get(canonical, ()))
        aliases += {"operator": ("操作人",), "note": ("备注",)}.get(key, ())
        normalized = {field.strip().lower(): field for field in fieldnames}
        return next((normalized[alias.lower()] for alias in aliases if alias.lower() in normalized), key)

    def apply_values(row: dict, values: dict) -> None:
        for key, value in values.items():
            column = column_for(key)
            if column not in fieldnames:
                fieldnames.append(column)
            row[column] = value

    # Retain historical rows, assignments and identifiers, even if removed from the source.
    for entry, row in zip(entries, rows):
        if (entry.status or "READY").upper() not in {"READY", "FAILED", "PARTIAL"}:
            continue
        media = resolve_path_maybe_relative(entry.media_path, plan_path.parent)
        record = record_index.get(media.name)
        if record is None:
            warnings.append(f"原任务保留，文案表已无对应行：{media.name}")
            continue
        values = {"title": record.social_title, "caption": record.emotional_description,
                  "hashtags": record.hashtags, "tracking_url": record.tracking_link}
        if not any((values["title"], values["caption"], values["hashtags"])):
            raise BitBrowserError(f"素材 {media.name} 的文案和标签均为空，请先补齐文案表。")
        if any(row.get(column_for(key), "") != value for key, value in values.items()):
            apply_values(row, values)
            result["updated"] += 1

    accounts = None
    for record in records:
        paths = media_index.get(record.video_filename, [])
        if not paths:
            warnings.append(f"未新增任务，缺少素材文件：{record.video_filename}（视频放 videos，图片放 images）")
            continue
        if len(paths) != 1:
            raise BitBrowserError(f"找到多个同名素材文件，无法确定文案对应关系：{record.video_filename}。请改为唯一文件名。")
        media = paths[0]
        kind = "video" if media.suffix.lower() in VIDEO_EXTENSIONS else "image"
        targets = routes.get(kind) or {"tiktok" if kind == "video" else "facebook": []}
        for platform, templates in targets.items():
            if (platform, media) in existing:
                continue
            if not any((record.social_title, record.emotional_description, record.hashtags)):
                raise BitBrowserError(f"素材 {media.name} 的文案和标签均为空，请先补齐文案表。")
            if accounts is None:
                usable = [account for account in load_account_ledger(ledger_path) if account.account_key and account.profile_id]
                for account in usable:
                    account.platform = normalize_platform_name(account.platform)
                account_ids = Counter((account.platform, account.account_key) for account in usable)
                if any(count != 1 for count in account_ids.values()):
                    raise BitBrowserError("台账存在同平台重复账号键，请先修正后刷新。")
                accounts = usable_accounts_by_platform(usable)
            account = choose_round_robin_account(accounts, account_counters, platform)
            if account is None:
                warnings.append(f"未新增任务，台账缺少可用的 {platform} 账号：{media.name}")
                continue

            def common_value(key: str, candidates: list) -> str:
                values = {getattr(entry, key) for entry in candidates if getattr(entry, key)}
                if len(values) > 1:
                    raise BitBrowserError(f"原计划的 {key} 有多个值，无法自动确定新任务归属或入口，请按客户/产品/入口拆分投放包。")
                return next(iter(values), "")

            args = argparse.Namespace(
                plan_client_id=common_value("client_id", templates or entries),
                plan_product_id=common_value("product_id", templates or entries),
                plan_operator=common_value("operator", templates or entries),
                plan_facebook_video_mode=common_value("facebook_content_mode", templates) or "post",
                plan_facebook_video_composer_url=common_value("composer_url", templates),
                plan_repeat=1, plan_attribution_prefix="", plan_note="", plan_scheduled_start="",
                plan_interval_minutes=0, plan_initial_status="READY",
            )
            sequence = len(rows) + 1
            generated = build_generated_plan_row(args, plan_path.parent, media, record, platform, kind, sequence, account)
            while generated["publish_id"] in ids:
                sequence += 1
                generated = build_generated_plan_row(args, plan_path.parent, media, record, platform, kind, sequence, account)
            ids[generated["publish_id"]] = 1
            if templates:
                generated["composer_url"] = common_value("composer_url", templates)
            new_row = {}
            apply_values(new_row, {field: generated.get(field, "") for field in PUBLISH_PLAN_FIELDS})
            rows.append(new_row)
            existing.add((platform, media))
            result["added"] += 1

    # Commit only after the full source has been checked; never truncate on an error.
    if result["added"] or result["updated"]:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", dir=plan_path.parent,
                                             prefix=plan_path.name + ".", suffix=".tmp", delete=False) as fh:
                temporary = Path(fh.name)
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            temporary.replace(plan_path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
    result["warnings"] = list(dict.fromkeys(warnings))
    return result
