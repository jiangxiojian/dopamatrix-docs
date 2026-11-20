"""Self-test the RPA operator console and confirmation workbench filters."""

from __future__ import annotations

import csv
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rpa_operator_console import generate_console  # noqa: E402
from rpa_workbench_server import WorkbenchConfig, WorkbenchError, WorkbenchState, render_page  # noqa: E402
from bitbrowser_rpa_example import generate_publish_plan, load_publish_plan, update_publish_plan_row  # noqa: E402
from bitbrowser_rpa_example import DEFAULT_DELIVERY_CSV_FILENAME, BitBrowserError  # noqa: E402
from rpa_csv import CSVFormatError, read_csv_table  # noqa: E402
from rpa_plan_sync import sync_delivery_plan  # noqa: E402
from dopa_matrix_publisher import fill_missing_plan_metadata  # noqa: E402


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_console() -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        plan_csv = root / "publish_plan.csv"
        summary_csv = root / "publish_summary.csv"
        log_jsonl = root / "publish_logs.jsonl"
        output_html = root / "rpa_operator_console.html"

        write_csv(
            plan_csv,
            [
                "publish_id",
                "platform",
                "status",
                "account_key",
                "profile_name",
                "client_id",
                "product_id",
                "media_path",
                "title",
                "tracking_url",
            ],
            [
                {
                    "publish_id": "PUB-001",
                    "platform": "facebook",
                    "status": "FAILED",
                    "account_key": "fb_test_sg_001",
                    "profile_name": "win-fb-001",
                    "client_id": "DMX",
                    "product_id": "RPA-ERROR-ACTION",
                    "media_path": "C:/tmp/fb.png",
                    "title": "FB test",
                    "tracking_url": "https://trk.example/one",
                },
                {
                    "publish_id": "PUB-002",
                    "platform": "tiktok",
                    "status": "PUBLISHED_MANUAL",
                    "account_key": "tk_test_sg_001",
                    "profile_name": "win-tk-001",
                    "client_id": "DMX",
                    "product_id": "RPA-OK",
                    "media_path": "C:/tmp/tk.mp4",
                    "title": "TK test",
                    "tracking_url": "https://trk.example/two",
                },
            ],
        )
        write_csv(
            summary_csv,
            [
                "publish_id",
                "platform",
                "status",
                "error_type",
                "error_message",
                "candidate_count",
                "candidate_sources",
                "scanned_tab_count",
                "scanner_error_count",
                "scanner_errors",
                "finished_at",
            ],
            [
                {
                    "publish_id": "PUB-001",
                    "platform": "facebook",
                    "status": "FAILED",
                    "error_type": "PROXY_CONNECTION_FAILED",
                    "error_message": "proxy failed",
                    "candidate_count": "2",
                    "candidate_sources": "tab_url | text:facebook_public_url",
                    "scanned_tab_count": "3",
                    "scanner_error_count": "1",
                    "scanner_errors": "error:RuntimeError https://www.facebook.com/ page closed",
                    "finished_at": "2026-08-20T10:30:00",
                },
                {
                    "publish_id": "PUB-002",
                    "platform": "tiktok",
                    "status": "PUBLISHED_MANUAL",
                    "finished_at": "2026-08-20T10:31:00",
                },
            ],
        )
        log_jsonl.write_text("{}", encoding="utf-8")

        args = type(
            "Args",
            (),
            {
                "plan_csv": str(plan_csv),
                "summary_csv": str(summary_csv),
                "log_jsonl": str(log_jsonl),
                "output_html": str(output_html),
            },
        )()
        generated = generate_console(args)
        if not generated.is_file():
            raise AssertionError(f"console not created: {generated}")
        return generated.read_text(encoding="utf-8")


def test_operator_console() -> None:
    html = run_console()
    assert_contains(html, "RPA 发布操作台", "console title")
    assert_contains(html, "全部建议 (2)", "action filter count")
    assert_contains(html, "data-filter-action=\"CHECK_PROXY\"", "proxy action filter")
    assert_contains(html, "data-filter-action=\"DONE\"", "done action filter")
    assert_contains(html, "检查代理 (CHECK_PROXY)", "proxy action label")
    assert_contains(html, "已完成 (DONE)", "done action label")
    assert_contains(html, "候选：2 / 来源：tab_url | text:facebook_public_url", "diagnostic summary")
    assert_contains(html, "扫描页签：3 / 扫描错误：1", "diagnostic counts")
    assert_contains(html, "error:RuntimeError https://www.facebook.com/ page closed", "diagnostic errors")
    assert_contains(html, "--log-jsonl", "log jsonl command")
    assert_contains(html, "--content-check-action cancel", "retry command")


def test_workbench_markup() -> None:
    html = render_page()
    assert_contains(html, "文件位置", "workbench compact sources")
    assert_contains(html, "1. 选择任务", "workbench operator guide")
    assert_contains(html, "任务列表", "workbench task list title")
    assert_contains(html, "展开详情 / 回填 / 账号健康", "workbench collapsed task details")
    assert_contains(html, "准备选中草稿", "workbench prepare button")
    assert_contains(html, "data-select=", "workbench task selection")
    assert_contains(html, "/api/prepare", "workbench prepare endpoint")
    assert_contains(html, "刷新投放表", "workbench delivery refresh button")
    assert_contains(html, "/api/refresh-delivery", "workbench delivery refresh endpoint")
    assert_contains(html, 'id="actionFilter"', "workbench action select")
    assert_contains(html, "全部建议", "workbench action label")
    assert_contains(html, "candidate_count", "workbench diagnostic search text")
    assert_contains(html, "诊断：候选", "workbench diagnostic summary")
    assert_contains(html, "task.error_action", "workbench action filter logic")
    assert_contains(html, "task.error_action_label", "workbench action label usage")
    assert_contains(html, "actionFilter.addEventListener('change', renderTasks);", "workbench change listener")


def test_workbench_prepare_tasks() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        plan_csv = root / "publish_plan.csv"
        ledger_csv = root / "账号环境台账.csv"
        write_csv(
            plan_csv,
            ["publish_id", "platform", "status", "account_key", "media_path"],
            [
                {
                    "publish_id": "PUB-READY",
                    "platform": "tiktok",
                    "status": "READY",
                    "account_key": "tk_test",
                    "media_path": "video.mp4",
                },
                {
                    "publish_id": "PUB-REJECTED",
                    "platform": "facebook",
                    "status": "REJECTED_MANUAL",
                    "account_key": "fb_test",
                    "media_path": "image.jpg",
                },
            ],
        )
        write_csv(ledger_csv, ["account_key", "platform", "profile_id"], [
            {"account_key": "tk_test", "platform": "tiktok", "profile_id": "profile-1"},
        ])
        config = WorkbenchConfig(
            plan_csv=plan_csv,
            log_jsonl=root / "publish_logs.jsonl",
            summary_csv=root / "publish_summary.csv",
            customer_report_detail_csv=root / "customer_report_seed.csv",
            customer_report_overview_csv=root / "customer_report_overview.csv",
            customer_report_html=root / "customer_report.html",
            account_health_csv=root / "rpa_account_health.csv",
            account_ledger_csv=ledger_csv,
            bit_api="http://127.0.0.1:54345",
            operator="tester",
        )
        state = WorkbenchState(config)
        captured: list[list[str]] = []

        entered = threading.Event()
        release = threading.Event()

        def fake_publisher_main(argv: list[str], progress_callback=None) -> int:
            captured.append(argv)
            progress_callback({"publish_id": "PUB-READY", "index": 1, "total": 1, "message": "Uploading"})
            entered.set()
            if not release.wait(5):
                raise AssertionError("test worker did not receive release")
            update_publish_plan_row(plan_csv, "PUB-READY", {"status": "PREPARED"})
            return 0

        with patch("rpa_workbench_server.publisher_main", fake_publisher_main):
            result = state.prepare_tasks({"publish_ids": ["PUB-READY"]})
            assert result["running"]
            assert entered.wait(5)
            try:
                assert state.preparation_status()["message"] == "Uploading"
                for operation in (
                    lambda: state.prepare_tasks({"publish_ids": ["PUB-READY"]}),
                    lambda: state.assign_account({"publish_id": "PUB-READY", "account_key": "tk_test"}),
                    lambda: state.backfill({"publish_id": "PUB-READY", "status": "READY"}),
                ):
                    try:
                        operation()
                    except WorkbenchError:
                        pass
                    else:
                        raise AssertionError("running batch allowed duplicate preparation or mutation")
            finally:
                release.set()
                state._prepare_thread.join(5)
            result = state.preparation_status()

        if result["running"] or result["exit_code"] != 0 or result["prepared"] != 1:
            raise AssertionError(f"unexpected prepare result: {result}")
        argv = captured[0]
        for needle in [
            "--only-publish-id",
            "PUB-READY",
            "--write-plan-status",
            "--tab-mode",
            "new",
            "--facebook-upload-mode",
            "auto",
            "--account-ledger",
            str(ledger_csv),
        ]:
            if needle not in argv:
                raise AssertionError(f"prepare argv missing {needle!r}: {argv}")

        # An exit code alone must not turn an unprepared task into a success.
        update_publish_plan_row(plan_csv, "PUB-READY", {"status": "READY"})
        with patch("rpa_workbench_server.publisher_main", lambda argv, **kwargs: 1):
            state.prepare_tasks({"publish_ids": ["PUB-READY"]})
            state._prepare_thread.join(5)
        assert state.preparation_status()["prepared"] == 0
        assert state.preparation_status()["needs_attention"] == 1
        with patch("rpa_workbench_server.publisher_main", side_effect=RuntimeError("connection lost")):
            state.prepare_tasks({"publish_ids": ["PUB-READY"]})
            state._prepare_thread.join(5)
        assert not state.preparation_status()["running"]
        assert state.preparation_status()["error"] == "connection lost"


def test_workbench_account_assignment() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        plan = root / "publish_plan.csv"
        ledger = root / "accounts.csv"
        write_csv(plan, ["发布ID", "平台", "状态", "账号键", "窗口ID"], [
            {"发布ID": "T1", "平台": "tiktok", "状态": "READY", "账号键": "tk1", "窗口ID": "old"},
            {"发布ID": "F1", "平台": "facebook", "状态": "PREPARED", "账号键": "fb1", "窗口ID": "shared"},
        ])
        write_csv(ledger, ["account_key", "platform", "profile_id", "profile_name"], [
            {"account_key": "tk1", "platform": "tiktok", "profile_id": "shared", "profile_name": "Shared"},
            {"account_key": "tk2", "platform": "tiktok", "profile_id": "second", "profile_name": "Second"},
            {"account_key": "fb1", "platform": "facebook", "profile_id": "shared", "profile_name": "Shared"},
        ])
        state = WorkbenchState(WorkbenchConfig(
            plan_csv=plan, log_jsonl=root / "log.jsonl", summary_csv=root / "summary.csv",
            customer_report_detail_csv=root / "detail.csv", customer_report_overview_csv=root / "overview.csv",
            customer_report_html=root / "report.html", account_health_csv=root / "health.csv",
            account_ledger_csv=ledger, bit_api="http://127.0.0.1:54345", operator="tester",
        ))
        assert state.find_task("T1")["assignment_error"]
        state.assign_account({"publish_id": "T1", "account_key": "tk2"})
        entry = load_publish_plan(plan)[0]
        assert (entry.account_key, entry.browser_profile_id) == ("tk2", "second")
        # Old execution summaries cannot overwrite a newly assigned account.
        write_csv(state.config.summary_csv, ["publish_id", "account_key", "profile_id", "status"], [
            {"publish_id": "T1", "account_key": "tk1", "profile_id": "old", "status": "FAILED"},
        ])
        task = state.find_task("T1")
        assert (task["account_key"], task["profile_id"], task["profile_name"], task["status"]) == ("tk2", "second", "Second", "READY")
        for publish_id, account_key in (("T1", "fb1"), ("T1", "missing"), ("F1", "fb1")):
            try:
                state.assign_account({"publish_id": publish_id, "account_key": account_key})
            except WorkbenchError:
                pass
            else:
                raise AssertionError("invalid or already-prepared assignment was accepted")
        state.assign_account({"publish_id": "T1", "account_key": "tk1"})
        assert not state.find_task("T1")["assignment_error"]
        assert state.find_task("T1")["profile_id"] == state.find_task("F1")["profile_id"] == "shared"
        with ledger.open("a", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerow(["tk1", "tiktok", "third", "Duplicate"])
        try:
            state.prepare_tasks({"publish_ids": ["T1"]})
        except WorkbenchError:
            pass
        else:
            raise AssertionError("duplicate account key was allowed to launch a browser")


def test_prepare_refreshes_selected_caption_without_restart() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        work = root / "rpa_work"
        work.mkdir()
        plan = work / "publish_plan.csv"
        ledger = root / "accounts.csv"
        source = root / DEFAULT_DELIVERY_CSV_FILENAME
        source_fields = ["视频文件名", "社交平台标题", "情绪化描述", "黄金标签", "追踪短链接"]
        write_csv(plan, ["publish_id", "platform", "status", "media_path", "account_key", "caption", "hashtags", "title", "tracking_url", "client_id"], [
            {"publish_id": "T1", "platform": "tiktok", "status": "PUBLISHED_MANUAL", "media_path": "../videos/first.mp4", "account_key": "tk1", "caption": "First caption", "hashtags": "#First", "client_id": "C1"},
            {"publish_id": "T2", "platform": "tiktok", "status": "READY", "media_path": "../videos/second.mp4", "account_key": "tk1", "caption": "First caption", "hashtags": "#First", "title": "First title", "client_id": "C2"},
        ])
        write_csv(ledger, ["account_key", "platform", "profile_id"], [
            {"account_key": "tk1", "platform": "tiktok", "profile_id": "profile-1"},
        ])
        state = WorkbenchState(WorkbenchConfig(
            plan_csv=plan, log_jsonl=work / "log.jsonl", summary_csv=work / "summary.csv",
            customer_report_detail_csv=work / "detail.csv", customer_report_overview_csv=work / "overview.csv",
            customer_report_html=work / "report.html", account_health_csv=work / "health.csv",
            account_ledger_csv=ledger, bit_api="http://127.0.0.1:1", operator="tester",
        ))
        state.snapshot()  # Open the workbench before the source is edited.
        source_rows = [
            {"视频文件名": "first.mp4", "情绪化描述": "First caption", "黄金标签": "#First"},
            {"视频文件名": "second.mp4", "社交平台标题": "Second title", "情绪化描述": "Pink, green, or yellow?", "黄金标签": "#Second", "追踪短链接": "https://example.test/second"},
        ]
        write_csv(source, source_fields, source_rows)
        captured = []

        def fake_run_single(args):
            captured.append(args)
            return {"plan": {"publish_id": args.publish_id}, "result": {"status": "PREPARED"}}

        with patch("bitbrowser_rpa_example.run_single", fake_run_single):
            state.prepare_tasks({"publish_ids": ["T2"]})
            state._prepare_thread.join(5)
        assert state.preparation_status()["prepared"] == 1
        assert len(captured) == 1
        assert captured[0].media.endswith("second.mp4")
        assert captured[0].caption == "Second title\n\nPink, green, or yellow?\n\n#Second"
        assert captured[0].client_id == "C2"
        assert captured[0].account_key == "tk1"
        assert state.find_task("T2")["caption"] == "Pink, green, or yellow?"
        assert load_publish_plan(plan)[0].status == "PUBLISHED_MANUAL"
        assert load_publish_plan(plan)[0].caption == "First caption"

        # Save a new source revision and retry using the same server object.
        update_publish_plan_row(plan, "T2", {"status": "READY"})
        source_rows[1].update({"社交平台标题": "", "情绪化描述": "Latest second caption", "黄金标签": "", "追踪短链接": ""})
        write_csv(source, source_fields, source_rows)
        with patch("bitbrowser_rpa_example.run_single", fake_run_single):
            state.prepare_tasks({"publish_ids": ["T2"]})
            state._prepare_thread.join(5)
        assert captured[1].caption == "Latest second caption"
        second = load_publish_plan(plan)[1]
        assert second.title == second.hashtags == second.tracking_url == ""
        assert second.account_key == "tk1" and second.client_id == "C2"

        update_publish_plan_row(plan, "T2", {"status": "READY"})
        before = plan.read_bytes()
        for invalid_source, expected_error in (
            ([source_rows[0]], BitBrowserError),
            ([*source_rows, source_rows[1]], BitBrowserError),
        ):
            write_csv(source, source_fields, invalid_source)
            try:
                state.prepare_tasks({"publish_ids": ["T2"]})
            except expected_error:
                pass
            else:
                raise AssertionError("invalid source started a preparation")
            assert plan.read_bytes() == before
            assert not state.preparation_status()["running"]
        source.write_text('video_filename,caption\nsecond.mp4,Pink, green, or yellow?\n', encoding="utf-8-sig")
        try:
            state.prepare_tasks({"publish_ids": ["T2"]})
        except CSVFormatError:
            pass
        else:
            raise AssertionError("malformed CSV started a preparation")
        assert plan.read_bytes() == before
        assert len(captured) == 2

        fields, rows = read_csv_table(plan)
        write_csv(plan, fields, [*rows, rows[1]])
        try:
            state.prepare_tasks({"publish_ids": ["T2"]})
        except WorkbenchError as exc:
            assert "任务 ID 重复" in str(exc)
        else:
            raise AssertionError("duplicate publish IDs started both materials")


def test_generated_plan_uses_rpa_work() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        delivery_csv = root / "矩阵投放文案对照表.csv"
        ledger_csv = root / "账号环境台账.csv"
        videos_dir = root / "videos"
        images_dir = root / "images"
        videos_dir.mkdir()
        images_dir.mkdir()
        (videos_dir / "demo_video.mp4").write_bytes(b"video")
        (images_dir / "demo_image.jpg").write_bytes(b"image")
        write_csv(
            delivery_csv,
            ["视频文件名", "社交平台标题", "情绪化描述", "黄金标签", "追踪短链接"],
            [
                {
                    "视频文件名": "demo_video.mp4",
                    "社交平台标题": "Video title",
                    "情绪化描述": "Video caption",
                    "黄金标签": "#video",
                    "追踪短链接": "https://trk.example/video",
                },
                {
                    "视频文件名": "demo_image.jpg",
                    "社交平台标题": "Image title",
                    "情绪化描述": "Image caption",
                    "黄金标签": "#image",
                    "追踪短链接": "https://trk.example/image",
                },
            ],
        )
        write_csv(
            ledger_csv,
            ["account_key", "platform", "profile_id"],
            [
                {"account_key": "tk_test", "platform": "tiktok", "profile_id": "tk-profile"},
                {"account_key": "fb_test", "platform": "facebook", "profile_id": "fb-profile"},
            ],
        )
        args = type(
            "Args",
            (),
            {
                "delivery_dir": str(root),
                "delivery_csv": "",
                "account_ledger": "",
                "output_plan_csv": "",
                "overwrite_plan": False,
                "plan_video_platforms": "tiktok",
                "plan_image_platforms": "facebook",
                "plan_repeat": 1,
                "plan_facebook_video_mode": "post",
                "plan_facebook_video_composer_url": "",
                "plan_client_id": "DMX",
                "plan_product_id": "RPA-WORK",
                "plan_operator": "tester",
                "plan_note": "",
                "plan_initial_status": "READY",
                "plan_scheduled_start": "",
                "plan_interval_minutes": 0,
                "plan_attribution_prefix": "",
            },
        )()
        result = generate_publish_plan(args)
        if result != 0:
            raise AssertionError(f"generate_publish_plan returned {result}")
        plan_csv = root / "rpa_work" / "publish_plan.csv"
        if not plan_csv.is_file():
            raise AssertionError(f"plan was not created in rpa_work: {plan_csv}")
        if (root / "publish_plan.csv").exists():
            raise AssertionError("legacy root publish_plan.csv should not be created")
        media_paths = {entry.media_path for entry in load_publish_plan(plan_csv)}
        if "../videos/demo_video.mp4" not in media_paths:
            raise AssertionError(f"video path should point back to videos: {media_paths}")
        if "../images/demo_image.jpg" not in media_paths:
            raise AssertionError(f"image path should point back to images: {media_paths}")


def test_fill_missing_plan_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        plan_csv = root / "publish_plan.csv"
        write_csv(
            plan_csv,
            ["publish_id", "client_id", "product_id", "operator", "status"],
            [
                {
                    "publish_id": "PUB-001",
                    "client_id": "",
                    "product_id": "",
                    "operator": "",
                    "status": "READY",
                },
                {
                    "publish_id": "PUB-002",
                    "client_id": "CUST-OLD",
                    "product_id": "PROD-OLD",
                    "operator": "old-op",
                    "status": "READY",
                },
            ],
        )

        changed = fill_missing_plan_metadata(plan_csv, "CUST-NEW", "PROD-NEW", "tester")
        if changed != 1:
            raise AssertionError(f"expected one changed row, got {changed}")

        with plan_csv.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        first, second = rows
        if first["client_id"] != "CUST-NEW" or first["product_id"] != "PROD-NEW" or first["operator"] != "tester":
            raise AssertionError(f"blank metadata was not filled: {first}")
        if second["client_id"] != "CUST-OLD" or second["product_id"] != "PROD-OLD" or second["operator"] != "old-op":
            raise AssertionError(f"existing metadata should not be overwritten: {second}")

        unchanged = fill_missing_plan_metadata(plan_csv, "CUST-OTHER", "PROD-OTHER", "other-op")
        if unchanged != 0:
            raise AssertionError(f"expected no overwrite, got {unchanged} changed rows")


def test_refresh_appends_media_and_preserves_history() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        work = root / "rpa_work"
        work.mkdir()
        (root / "videos").mkdir()
        (root / "images").mkdir()
        plan = work / "publish_plan.csv"
        ledger = root / "accounts.csv"
        source = root / DEFAULT_DELIVERY_CSV_FILENAME
        fields = ["视频文件名", "社交平台标题", "情绪化描述", "黄金标签", "追踪短链接"]
        source_rows = []
        initial_rows = []
        for number, status in enumerate(("PUBLISHED_MANUAL", "PREPARED", "READY"), 1):
            filename = f"video{number}.mp4"
            (root / "videos" / filename).write_bytes(b"offline")
            source_rows.append({"视频文件名": filename, "情绪化描述": f"Latest {number}", "黄金标签": f"#Tag{number}"})
            initial_rows.append({
                "publish_id": f"T{number}", "platform": "tiktok", "status": status,
                "media_path": "../videos/" + filename, "caption": f"Original {number}",
                "account_key": "tk1", "browser_profile_id": "shared", "client_id": "C1",
                "product_id": "P1", "scheduled_at": "2026-11-20T18:00:00", "custom_note": "Keep me",
                "post_url": "https://www.tiktok.com/@test/video/123" if number == 1 else "",
                "result_screenshot": "screenshots/old.png", "attribution_token": f"TOKEN{number}",
            })
        write_csv(plan, list(initial_rows[0]), initial_rows)
        write_csv(source, fields, source_rows)
        write_csv(ledger, ["account_key", "platform", "profile_id"], [
            {"account_key": "tk1", "platform": "tiktok", "profile_id": "shared"},
            {"account_key": "fb1", "platform": "facebook", "profile_id": "shared"},
        ])
        state = WorkbenchState(WorkbenchConfig(
            plan_csv=plan, log_jsonl=work / "log.jsonl", summary_csv=work / "summary.csv",
            customer_report_detail_csv=work / "detail.csv", customer_report_overview_csv=work / "overview.csv",
            customer_report_html=work / "report.html", account_health_csv=work / "health.csv",
            account_ledger_csv=ledger, bit_api="http://127.0.0.1:1", operator="tester",
        ))
        assert len(state.snapshot()["tasks"]) == 3
        source_rows.append({"视频文件名": "video4.mp4", "社交平台标题": "Fourth", "情绪化描述": "Pink, green, yellow", "黄金标签": "#Four"})
        (root / "videos" / "video4.mp4").write_bytes(b"offline")
        write_csv(source, fields, source_rows)
        with patch("rpa_workbench_server.publisher_main") as publisher:
            result = state.refresh_delivery()
            publisher.assert_not_called()
        assert (result["added"], result["updated"], result["warnings"]) == (1, 1, [])
        rows = read_csv_table(plan)[1]
        for index in (0, 1):
            assert {key: rows[index][key] for key in initial_rows[index]} == initial_rows[index]
        assert rows[2]["caption"] == "Latest 3"
        assert rows[2]["account_key"] == "tk1" and rows[2]["custom_note"] == "Keep me"
        fourth = load_publish_plan(plan)[3]
        assert (fourth.title, fourth.caption, fourth.hashtags, fourth.status) == ("Fourth", "Pink, green, yellow", "#Four", "READY")
        assert (fourth.client_id, fourth.product_id, fourth.platform, fourth.account_key) == ("C1", "P1", "tiktok", "tk1")
        assert fourth.media_path == "../videos/video4.mp4" and not fourth.scheduled_at
        assert len(state.snapshot()["tasks"]) == 4
        saved = plan.read_bytes()
        assert state.refresh_delivery()["added"] == 0
        assert plan.read_bytes() == saved

        # A CSV row without its file is visible as a warning, and can be retried later.
        source_rows.append({"视频文件名": "photo.jpg", "情绪化描述": "Photo caption"})
        write_csv(source, fields, source_rows)
        result = state.refresh_delivery()
        assert result["added"] == 0 and "photo.jpg" in " ".join(result["warnings"])
        (root / "images" / "photo.jpg").write_bytes(b"offline")
        result = state.refresh_delivery()
        assert result["added"] == 1 and not result["warnings"]
        photo = load_publish_plan(plan)[4]
        assert (photo.platform, photo.content_type, photo.account_key) == ("facebook", "image", "fb1")
        assert state.refresh_delivery()["added"] == 0
        state._preparation = {"running": True}
        try:
            state.refresh_delivery()
        except WorkbenchError:
            pass
        else:
            raise AssertionError("delivery refresh changed a running batch")


def test_refresh_validation_and_legacy_columns() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "videos").mkdir()
        for filename in ("old.mp4", "new.mp4"):
            (root / "videos" / filename).write_bytes(b"offline")
        plan = root / "publish_plan.csv"
        ledger = root / "accounts.csv"
        source = root / DEFAULT_DELIVERY_CSV_FILENAME
        source_fields = ["视频文件名", "情绪化描述", "黄金标签"]
        source_rows = [{"视频文件名": name, "情绪化描述": "Caption " + name} for name in ("old.mp4", "new.mp4")]
        write_csv(plan, ["发布ID", "平台", "状态", "素材路径", "文案", "账号键", "客户ID", "产品ID", "FB内容模式", "入口URL"], [
            {"发布ID": "F1", "平台": "facebook", "状态": "PUBLISHED_MANUAL", "素材路径": "videos/old.mp4",
             "文案": "Published", "账号键": "fb1", "客户ID": "C1", "产品ID": "P1", "FB内容模式": "reel", "入口URL": "https://example.test/reels"},
        ])
        write_csv(ledger, ["account_key", "platform", "profile_id"], [{"account_key": "fb1", "platform": "facebook", "profile_id": "shared"}])
        write_csv(source, source_fields, [*source_rows, source_rows[1]])
        saved = plan.read_bytes()
        try:
            sync_delivery_plan(plan, ledger)
        except BitBrowserError:
            pass
        else:
            raise AssertionError("duplicate source filenames accepted")
        assert plan.read_bytes() == saved
        write_csv(source, source_fields, source_rows)
        (root / "duplicate").mkdir()
        duplicate = root / "duplicate" / "new.mp4"
        duplicate.write_bytes(b"offline")
        try:
            sync_delivery_plan(plan, ledger)
        except BitBrowserError:
            pass
        else:
            raise AssertionError("ambiguous media files accepted")
        assert plan.read_bytes() == saved
        duplicate.unlink()
        source.write_text('video_filename,caption\nnew.mp4,One, two\n', encoding="utf-8-sig")
        try:
            sync_delivery_plan(plan, ledger)
        except CSVFormatError:
            pass
        else:
            raise AssertionError("malformed source accepted")
        assert plan.read_bytes() == saved
        write_csv(source, source_fields, source_rows)
        assert sync_delivery_plan(plan, ledger)["added"] == 1
        fields, rows = read_csv_table(plan)
        assert "平台" in fields and "platform" not in fields
        assert "素材路径" in fields and "media_path" not in fields
        assert "文案" in fields and "caption" not in fields
        new = load_publish_plan(plan)[1]
        assert new.facebook_content_mode == "reel" and new.composer_url == "https://example.test/reels"
        assert new.platform == "facebook" and new.status == "READY"
        assert new.client_id == "C1" and new.product_id == "P1"
        write_csv(source, source_fields, [source_rows[1]])
        assert sync_delivery_plan(plan, ledger)["added"] == 0
        assert len(load_publish_plan(plan)) == 2  # Removing a source row never deletes history.


def main() -> int:
    test_operator_console()
    print("PASS test_operator_console")
    test_workbench_markup()
    print("PASS test_workbench_markup")
    test_workbench_prepare_tasks()
    print("PASS test_workbench_prepare_tasks")
    test_workbench_account_assignment()
    print("PASS test_workbench_account_assignment")
    test_prepare_refreshes_selected_caption_without_restart()
    print("PASS test_prepare_refreshes_selected_caption_without_restart")
    test_generated_plan_uses_rpa_work()
    print("PASS test_generated_plan_uses_rpa_work")
    test_fill_missing_plan_metadata()
    print("PASS test_fill_missing_plan_metadata")
    test_refresh_appends_media_and_preserves_history()
    print("PASS test_refresh_appends_media_and_preserves_history")
    test_refresh_validation_and_legacy_columns()
    print("PASS test_refresh_validation_and_legacy_columns")
    print("RPA operator console self-test passed: 9 groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
