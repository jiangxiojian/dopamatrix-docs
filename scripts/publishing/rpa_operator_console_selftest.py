"""Self-test the RPA operator console and confirmation workbench filters."""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rpa_operator_console import generate_console  # noqa: E402
from rpa_workbench_server import WorkbenchConfig, WorkbenchState, render_page  # noqa: E402


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
    assert_contains(html, "准备选中草稿", "workbench prepare button")
    assert_contains(html, "data-select=", "workbench task selection")
    assert_contains(html, "/api/prepare", "workbench prepare endpoint")
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
        write_csv(ledger_csv, ["account_key", "platform", "profile_id"], [])
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

        def fake_publisher_main(argv: list[str]) -> int:
            captured.append(argv)
            return 0

        with patch("rpa_workbench_server.publisher_main", fake_publisher_main):
            result = state.prepare_tasks({"publish_ids": ["PUB-READY"]})

        if result["exit_code"] != 0 or result["prepared"] != 1:
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


def main() -> int:
    test_operator_console()
    print("PASS test_operator_console")
    test_workbench_markup()
    print("PASS test_workbench_markup")
    test_workbench_prepare_tasks()
    print("PASS test_workbench_prepare_tasks")
    print("RPA operator console self-test passed: 3 groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
