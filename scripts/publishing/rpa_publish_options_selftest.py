"""Regression checks for cover assets, time zones and content confirmations."""

from __future__ import annotations

import base64
import io
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from bitbrowser_rpa_example import scan_media_files, update_publish_plan_row, IMAGE_EXTENSIONS
from rpa_operator_console_selftest import write_csv
from rpa_publish_options import (DEFAULT_OPTIONS, PublishOptionsStore, delivery_copy, digest, hash_file,
                                 import_cover, scheduled_utc, validate_options)
from rpa_workbench_server import WorkbenchConfig, WorkbenchError, WorkbenchState


def must_fail(action, error=ValueError):
    try:
        action()
    except error:
        return
    raise AssertionError("Invalid publishing settings or confirmation were accepted")


def png_bytes(color="red"):
    buffer = io.BytesIO()
    Image.new("RGB", (80, 120), color).save(buffer, format="PNG")
    return buffer.getvalue()


def make_state(root):
    work = root / "rpa_work"
    work.mkdir()
    (root / "videos").mkdir()
    plan = work / "publish_plan.csv"
    ledger = root / "accounts.csv"
    rows = []
    copy = []
    for number in (1, 2):
        name = f"video{number}.mp4"
        (root / "videos" / name).write_bytes(f"video bytes {number}".encode())
        rows.append({"publish_id": f"T{number}", "platform": "tiktok", "content_type": "video", "status": "READY",
                     "account_key": "tk1", "browser_profile_id": "001", "media_path": "../videos/" + name,
                     "title": f"Title {number}", "caption": f"Caption {number}", "hashtags": f"#Tag{number}", "tracking_url": ""})
        copy.append({"视频文件名": name, "社交平台标题": f"Title {number}", "情绪化描述": f"Caption {number}", "黄金标签": f"#Tag{number}", "追踪短链接": ""})
    write_csv(plan, list(rows[0]), rows)
    write_csv(ledger, ["account_key", "platform", "profile_id"], [
        {"account_key": "tk1", "platform": "tiktok", "profile_id": "001"},
        {"account_key": "tk2", "platform": "tiktok", "profile_id": "test-other"},
    ])
    write_csv(root / "矩阵投放文案对照表.csv", list(copy[0]), copy)
    return WorkbenchState(WorkbenchConfig(plan, work / "log.jsonl", work / "summary.csv", work / "detail.csv",
                          work / "overview.csv", work / "report.html", work / "health.csv", ledger,
                          "http://127.0.0.1:1", "tester")), copy


def confirm(state, ids):
    versions = {publish_id: state.find_task(publish_id)["publication"]["review_version"] for publish_id in ids}
    state.confirm_content({"publish_ids": ids, "versions": versions, "operator": "Alice"})
    state._confirmation_thread.join(5)
    assert not state.confirmation_status()["running"]
    return state.confirmation_status()


def test_cover_import_and_exclusion():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        data = base64.b64encode(png_bytes()).decode()
        path = import_cover(root, "../../my cover.png", data)
        assert path.startswith("covers/") and (root / path).is_file()
        assert import_cover(root, "../../my cover.png", data) == path
        assert scan_media_files(root, IMAGE_EXTENSIONS) == []
        (root / "images").mkdir()
        (root / "images" / "post.png").write_bytes(png_bytes())
        assert [item.name for item in scan_media_files(root, IMAGE_EXTENSIONS)] == ["post.png"]
        task = {"platform": "tiktok", "content_type": "video", "media_path": "videos/demo.mp4"}
        options = validate_options(root, task, {"cover_mode": "image", "cover_path": path})
        assert options["cover_path"] == path
        must_fail(lambda: validate_options(root, task, {"cover_mode": "image", "cover_path": "images/post.png"}))
        must_fail(lambda: validate_options(root, {**task, "content_type": "image"}, options))
        must_fail(lambda: import_cover(root, "bad.png", base64.b64encode(b"not an image").decode()))
        must_fail(lambda: import_cover(root, "bad.png", "!@#$"))
        must_fail(lambda: validate_options(root, task, {"cover_mode": []}))


def test_timezones_and_invalid_options():
    clock = datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert scheduled_utc("2027-06-01T12:00", "America/New_York", clock) == "2027-06-01T16:00:00+00:00"
    assert scheduled_utc("2027-06-01T12:00", "Asia/Shanghai", clock) == "2027-06-01T04:00:00+00:00"
    for local, zone in (("2027-03-14T02:30", "America/New_York"), ("2027-11-07T01:30", "America/New_York"),
                        ("2026-01-01T12:00", "UTC"), ("garbage", "UTC"), ("2027-06-01T12:00+08:00", "UTC")):
        must_fail(lambda: scheduled_utc(local, zone, clock))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        task = {"platform": "facebook"}
        must_fail(lambda: validate_options(root, task, {"visibility": "private"}))
        must_fail(lambda: validate_options(root, task, {"publish_mode": "submit-now"}))
        options = validate_options(root, task, {"publish_mode": "platform_schedule", "publish_time": "2099-06-01T12:00", "timezone": "Asia/Shanghai"})
        assert options["publish_at_utc"] == "2099-06-01T04:00:00+00:00"
        assert validate_options(root, task, {**options, "publish_mode": "manual"})["publish_at_utc"] == ""


def test_confirmation_invalidation_and_full_file_check():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        state, copy = make_state(root)
        before = state.config.plan_csv.read_bytes()
        write_csv(state.config.summary_csv, ["publish_id", "platform", "media_path", "client_id"], [
            {"publish_id": "T1", "platform": "facebook", "media_path": "../videos/video2.mp4", "client_id": "OLD"},
        ])
        assert state.find_task("T1")["media_path"] == "../videos/video1.mp4"
        assert state.find_task("T1")["platform"] == "tiktok"
        assert state.find_task("T1")["client_id"] == ""
        assert confirm(state, ["T1", "T2"])["confirmed"] == 2
        task = state.find_task("T1")
        assert task["publication"]["confirmation_status"] == "CONFIRMED"
        assert not task["publication"]["execution_enabled"]
        assert state.options_store.verify_confirmation(task)
        assert state.config.plan_csv.read_bytes() == before
        assert not state.config.log_jsonl.exists()
        # An unrelated new source row cannot invalidate existing confirmations.
        copy.append({**copy[0], "视频文件名": "third.mp4", "情绪化描述": "Third"})
        write_csv(root / "矩阵投放文案对照表.csv", list(copy[0]), copy)
        assert state.find_task("T1")["publication"]["confirmation_status"] == "CONFIRMED"
        copy[0]["情绪化描述"] = "Changed source"
        write_csv(root / "矩阵投放文案对照表.csv", list(copy[0]), copy)
        assert state.find_task("T1")["publication"]["confirmation_status"] == "STALE"
        assert state.find_task("T2")["publication"]["confirmation_status"] == "CONFIRMED"
        state.refresh_delivery()
        assert confirm(state, ["T1"])["confirmed"] == 1
        task = state.find_task("T1")
        media = root / "videos" / "video1.mp4"
        stamp = media.stat()
        media.write_bytes(b"x" * stamp.st_size)
        os.utime(media, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        # UI metadata is only a quick indication; forced checksum verification catches this.
        assert not state.options_store.verify_confirmation(task)
        assert confirm(state, ["T1"])["confirmed"] == 1
        state.assign_account({"publish_id": "T1", "account_key": "tk2"})
        assert state.find_task("T1")["publication"]["confirmation_status"] == "STALE"
        task = state.find_task("T2")
        state.save_publish_options({"publish_id": "T2", "settings_version": task["publication"]["settings_version"],
                                    "options": {"publish_mode": "auto_now"}})
        assert state.find_task("T2")["publication"]["confirmation_status"] == "STALE"
        changed = state.find_task("T2")
        state.save_publish_options({"publish_id": "T2", "settings_version": changed["publication"]["settings_version"], "options": DEFAULT_OPTIONS})
        assert state.find_task("T2")["publication"]["confirmation_status"] == "STALE"  # Changing back does not revive a prior confirmation.
        changed = state.find_task("T2")
        state.save_publish_options({"publish_id": "T2", "settings_version": changed["publication"]["settings_version"], "options": {"publish_mode": "auto_now"}})
        must_fail(lambda: state.save_publish_options({"publish_id": "T2", "settings_version": task["publication"]["settings_version"], "options": DEFAULT_OPTIONS}))
        restarted = WorkbenchState(state.config)
        assert restarted.find_task("T2")["publication"]["options"]["publish_mode"] == "auto_now"
        update_publish_plan_row(state.config.plan_csv, "T2", {"status": "PREPARED"})
        must_fail(lambda: state.save_publish_options({"publish_id": "T2"}), WorkbenchError)


def test_atomic_batch_background_and_failure():
    with tempfile.TemporaryDirectory() as directory:
        state, _ = make_state(Path(directory))
        source = delivery_copy(state.options_store.root)
        task = state.find_task("T1")
        old_version = task["publication"]["review_version"]
        update_publish_plan_row(state.config.plan_csv, "T1", {"title": "Changed"})
        must_fail(lambda: state.confirm_content({"publish_ids": ["T1"], "versions": {"T1": old_version}, "operator": "Alice"}), WorkbenchError)
        update_publish_plan_row(state.config.plan_csv, "T1", {"title": "Title 1"})
        before = state.config.plan_csv.read_bytes()
        started = threading.Event()
        released = threading.Event()
        original_hash = hash_file

        def blocking_hash(path):
            started.set()
            if not released.wait(5):
                raise RuntimeError("test release timed out")
            if path.name == "video2.mp4":
                raise ValueError("Second media failed")
            return original_hash(path)

        try:
            with patch("rpa_publish_options.hash_file", side_effect=blocking_hash), patch("rpa_workbench_server.publisher_main") as publisher:
                ids = ["T1", "T2"]
                state.confirm_content({"publish_ids": ids, "versions": {item: state.find_task(item)["publication"]["review_version"] for item in ids}, "operator": "Alice"})
                assert started.wait(2)
                assert state.snapshot()["confirmation"]["running"]
                for action in (lambda: state.prepare_tasks({"publish_ids": ["T1"]}), state.refresh_delivery,
                               lambda: state.inspect_entry({"publish_id": "T1"})):
                    must_fail(action, WorkbenchError)
                released.set()
                state._confirmation_thread.join(5)
                publisher.assert_not_called()
            assert state.confirmation_status()["confirmed"] == 0
            assert "Second media failed" in state.confirmation_status()["error"]
            assert not state.options_store.path.exists()  # No partial confirmation of the first item.
            assert state.config.plan_csv.read_bytes() == before
            assert confirm(state, ["T1"])["confirmed"] == 1
            state.options_store.path.write_text("broken JSON", encoding="utf-8")
            must_fail(lambda: state.options_store.read())
        finally:
            released.set()
            if hasattr(state, "_confirmation_thread"):
                state._confirmation_thread.join(5)


def main():
    for test in (test_cover_import_and_exclusion, test_timezones_and_invalid_options,
                 test_confirmation_invalidation_and_full_file_check, test_atomic_batch_background_and_failure):
        test()
        print("PASS " + test.__name__)
    print("Publishing settings self-test passed: 4 groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
