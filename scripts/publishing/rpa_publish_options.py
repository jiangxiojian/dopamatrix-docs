"""Persist publishing presets and content confirmations; never submit posts."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image

from bitbrowser_rpa_example import DEFAULT_DELIVERY_CSV_FILENAME, DEFAULT_WORK_DIRNAME, load_delivery_records

DEFAULT_OPTIONS = {
    "publish_mode": "manual", "cover_mode": "platform", "cover_path": "",
    "publish_time": "", "timezone": "Asia/Shanghai", "publish_at_utc": "",
    "visibility": "platform_default", "commercial_content": "unset", "ai_content": "unset",
}
OPTION_CHOICES = {
    "publish_mode": {"manual", "auto_now", "platform_schedule"},
    "cover_mode": {"platform", "image"},
    "visibility": {"platform_default", "public", "private"},
    "commercial_content": {"unset", "yes", "no"}, "ai_content": {"unset", "yes", "no"},
}
TIMEZONES = ("Asia/Shanghai", "Asia/Singapore", "Asia/Manila", "UTC", "America/New_York", "America/Los_Angeles", "Europe/London")
MAX_COVER_BYTES = 8 * 1024 * 1024
COPY_FIELDS = ("title", "caption", "hashtags", "tracking_url")
CONTENT_FIELDS = ("publish_id", "platform", "content_type", "facebook_content_mode", "composer_url", "account_key",
                  "profile_id", "media_path", "client_id", "product_id", "title", "caption", "hashtags", "tracking_url",
                  "attribution_token", "scheduled_at")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def package_root(plan_path: Path) -> Path:
    return plan_path.parent.parent if plan_path.parent.name == DEFAULT_WORK_DIRNAME else plan_path.parent


def resolve_cover(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to((root / "covers").resolve()) or not path.is_relative_to(root.resolve()):
        raise ValueError("封面需保存在当前投放包的 covers 文件夹中。")
    if not path.is_file():
        raise ValueError("所选封面文件不存在，请重新选择。")
    return path


def inspect_image(data: bytes) -> tuple[str, tuple[int, int]]:
    if not data or len(data) > MAX_COVER_BYTES:
        raise ValueError("请选择不超过 8 MB 的 JPG、PNG 或 WebP 封面。")
    try:
        with Image.open(io.BytesIO(data)) as image:
            suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(image.format)
            size = image.size
            if suffix is None or size[0] * size[1] > 40_000_000 or min(size) < 1:
                raise ValueError("封面格式或尺寸不适合预览，请选择普通 JPG、PNG 或 WebP 图片。")
            if getattr(image, "is_animated", False):
                raise ValueError("请使用静态封面图片。")
            image.verify()
        return suffix, size
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("封面图片无法读取，请重新导出 JPG 或 PNG。") from exc


def import_cover(root: Path, name: str, encoded: str) -> str:
    if not isinstance(encoded, str) or len(encoded) > (MAX_COVER_BYTES * 4 // 3 + 8):
        raise ValueError("封面文件超过 8 MB。")
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("封面传输内容不完整，请重新选择文件。") from exc
    suffix, _ = inspect_image(data)
    stem = re.sub(r"[^\w.-]", "_", Path(name).stem)[:40].strip(".") or "cover"
    filename = f"{stem}-{hashlib.sha256(data).hexdigest()[:16]}{suffix}"
    directory = root / "covers"
    directory.mkdir(parents=True, exist_ok=True)
    target = (directory / filename).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("封面目录不在当前投放包中。")
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("封面文件名冲突，请重命名图片后导入。")
    else:
        target.write_bytes(data)
    return target.relative_to(root.resolve()).as_posix()


def scheduled_utc(local_text: str, zone_name: str, now: datetime | None = None) -> str:
    try:
        local = datetime.fromisoformat(local_text)
        zone = ZoneInfo(zone_name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("请选择有效的日期、时间和时区。") from exc
    if local.tzinfo is not None:
        raise ValueError("日期时间字段请填写当地时间，时区在右侧选择。")
    candidates = set()
    for fold in (0, 1):
        utc = local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == local:
            candidates.add(utc)
    if len(candidates) != 1:
        raise ValueError("所选时间处于夏令时跳时或重复时段，请换一个明确的当地时间。")
    utc = next(iter(candidates))
    if utc <= (now or datetime.now(timezone.utc)):
        raise ValueError("预设发布时间需晚于当前时间。")
    return utc.isoformat(timespec="seconds")


def validate_options(root: Path, task: dict[str, Any], values: dict[str, Any]) -> dict[str, str]:
    if not isinstance(values, dict):
        raise ValueError("发布设置格式错误。")
    options = dict(DEFAULT_OPTIONS)
    for key in options:
        value = values.get(key, options[key])
        if not isinstance(value, str):
            raise ValueError("发布设置应为文本选项。")
        options[key] = value.strip()
    for key, choices in OPTION_CHOICES.items():
        if options[key] not in choices:
            raise ValueError(f"发布设置选项无效：{key}")
    if options["timezone"] not in TIMEZONES:
        raise ValueError("请选择列表中的时区。")
    if options["visibility"] == "private" and task.get("platform") != "tiktok":
        raise ValueError("当前仅为 TK 提供“仅自己”预设；FB Page 请选平台默认或公开。")
    if options["cover_mode"] == "image":
        media = Path(task.get("media_path") or "")
        if task.get("content_type") == "image" or media.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("图片帖直接使用图片素材，无需另设视频封面。")
        cover = resolve_cover(root, options["cover_path"])
        if cover.stat().st_size > MAX_COVER_BYTES:
            raise ValueError("封面文件超过 8 MB。")
        inspect_image(cover.read_bytes())
        options["cover_path"] = cover.relative_to(root.resolve()).as_posix()
    else:
        options["cover_path"] = ""
    if options["publish_mode"] == "platform_schedule":
        options["publish_at_utc"] = scheduled_utc(options["publish_time"], options["timezone"])
    else:
        options["publish_time"] = options["publish_at_utc"] = ""
    return options


def delivery_copy(root: Path) -> dict[str, Any]:
    source = root / DEFAULT_DELIVERY_CSV_FILENAME
    if not source.exists():
        return {"present": False, "records": {}, "error": ""}
    try:
        records: dict[str, list[dict[str, str]]] = {}
        for record in load_delivery_records(source):
            records.setdefault(record.video_filename, []).append(dict(zip(COPY_FIELDS, (
                record.social_title, record.emotional_description, record.hashtags, record.tracking_link,
            ))))
        return {"present": True, "records": records, "error": ""}
    except (ValueError, OSError, RuntimeError) as exc:
        return {"present": True, "records": {}, "error": f"文案表无法校验，请先修正后刷新：{exc}"}


def file_stamp(path: Path) -> dict[str, Any]:
    stat = path.stat()
    if not path.is_file():
        raise ValueError("素材不是普通文件。")
    return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def hash_file(path: Path) -> str:
    before = file_stamp(path)
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            sha.update(chunk)
    if before != file_stamp(path):
        raise ValueError("文件正在变化，请等待复制完成后重新确认。")
    return sha.hexdigest()


def review_version(plan_path: Path, task: dict[str, Any], options: dict[str, str], source: dict[str, Any]) -> tuple[str, str]:
    fields = {key: task.get(key, "") for key in CONTENT_FIELDS}
    evidence: dict[str, Any] = {"task": fields, "options": options, "source_present": source["present"]}
    error = task.get("assignment_error") or source["error"]
    try:
        media = (plan_path.parent / task.get("media_path", "")).resolve()
        if not task.get("media_path"):
            raise ValueError("任务缺少素材路径。")
        evidence["media"] = file_stamp(media)
        if options["cover_mode"] == "image":
            evidence["cover"] = file_stamp(resolve_cover(package_root(plan_path), options["cover_path"]))
        if source["present"] and not source["error"]:
            matches = source["records"].get(media.name, [])
            evidence["source_copy"] = matches
            if len(matches) != 1:
                error = "文案表缺少唯一对应行，请修正后刷新投放表。"
            elif matches[0] != {key: task.get(key, "") for key in COPY_FIELDS}:
                error = "文案表已变化，请先刷新投放表，核对最新内容后再确认。"
    except (OSError, ValueError) as exc:
        error = f"素材或封面无法核对：{exc}"
        evidence["file_error"] = str(exc)
    return digest(evidence), str(error or "")


class PublishOptionsStore:
    def __init__(self, plan_path: Path):
        self.plan_path = plan_path
        self.root = package_root(plan_path)
        self.path = plan_path.parent / "publish_options.json"

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "tasks": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") != 1 or not isinstance(data.get("tasks"), dict):
                raise ValueError("结构错误")
            for record in data["tasks"].values():
                if not isinstance(record, dict) or not isinstance(record.get("options", {}), dict):
                    raise ValueError("任务记录结构错误")
                if any(not isinstance(value, str) for key, value in record.get("options", {}).items() if key in DEFAULT_OPTIONS):
                    raise ValueError("任务设置值类型错误")
                if not isinstance(record.get("confirmation", {}), dict):
                    raise ValueError("内容确认记录结构错误")
            return data
        except (ValueError, OSError, AttributeError) as exc:
            raise ValueError(f"发布设置文件无法读取，请保留文件并检查：{self.path}") from exc

    def write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=self.path.parent, suffix=".tmp", delete=False) as fh:
                temporary = Path(fh.name)
                json.dump(data, fh, ensure_ascii=False, indent=2)
            temporary.replace(self.path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def options(self, data: dict, publish_id: str) -> dict[str, str]:
        values = data["tasks"].get(publish_id, {}).get("options", {})
        return {**DEFAULT_OPTIONS, **{key: values[key] for key in DEFAULT_OPTIONS if key in values}}

    def view(self, data: dict, task: dict[str, Any], source: dict) -> dict[str, Any]:
        options = self.options(data, task["publish_id"])
        version, error = review_version(self.plan_path, task, options, source)
        confirmation = data["tasks"].get(task["publish_id"], {}).get("confirmation") or {}
        status = "CONFIRMED" if confirmation.get("version") == version and not error and not confirmation.get("invalidated_at") else "STALE" if confirmation else "UNCONFIRMED"
        return {"options": options, "settings_version": digest(options), "review_version": version,
                "confirmation_status": status, "confirmation_error": error,
                "confirmed_by": confirmation.get("operator", ""), "confirmed_at": confirmation.get("confirmed_at", ""),
                "execution_enabled": False}

    def save_settings(self, task: dict[str, Any], values: dict, expected_version: str) -> dict[str, str]:
        data = self.read()
        current = self.options(data, task["publish_id"])
        if expected_version != digest(current):
            raise ValueError("设置已在其他页面修改，请刷新后再保存。")
        options = validate_options(self.root, task, values)
        record = data["tasks"].setdefault(task["publish_id"], {})
        if options != current:
            if record.get("confirmation"):
                record["confirmation"]["invalidated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        record["options"] = options
        self.write(data)
        return options

    def build_confirmation(self, task: dict[str, Any], expected_version: str, operator: str) -> dict[str, Any]:
        if not operator.strip():
            raise ValueError("请填写确认人。")
        data = self.read()
        options = self.options(data, task["publish_id"])
        validate_options(self.root, task, options)
        version, error = review_version(self.plan_path, task, options, delivery_copy(self.root))
        if error or version != expected_version:
            raise ValueError(error or "内容或文件已变化，请刷新并核对后重新确认。")
        media = (self.plan_path.parent / task["media_path"]).resolve()
        hashes = {"media": hash_file(media)}
        if options["cover_mode"] == "image":
            hashes["cover"] = hash_file(resolve_cover(self.root, options["cover_path"]))
        after, after_error = review_version(self.plan_path, task, options, delivery_copy(self.root))
        if after != version or after_error:
            raise ValueError("确认期间内容发生变化，请重新核对。")
        return {"version": version, "hashes": hashes, "operator": operator.strip(),
                "confirmed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "task": {key: task.get(key, "") for key in CONTENT_FIELDS}, "options": options,
                "purpose": "content_review_only"}

    def verify_confirmation(self, task: dict[str, Any]) -> bool:
        """Full check for a future executor; a list-page metadata check is insufficient."""
        data = self.read()
        view = self.view(data, task, delivery_copy(self.root))
        if view["confirmation_status"] != "CONFIRMED":
            return False
        stored = data["tasks"][task["publish_id"]]["confirmation"]
        try:
            latest = self.build_confirmation(task, view["review_version"], stored["operator"])
        except (OSError, ValueError):
            return False
        return latest["hashes"] == stored["hashes"]
