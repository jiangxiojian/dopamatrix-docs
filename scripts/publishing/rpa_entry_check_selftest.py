"""Exercise read-only entry inspection, persistence and background task guards."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rpa_entry_check import classify_page, inspect_context, load_report, matches_platform, report_path, save_report
from rpa_operator_console_selftest import write_csv
from rpa_workbench_server import WorkbenchConfig, WorkbenchError, WorkbenchState


def test_platform_and_capability_evidence() -> None:
    assert matches_platform("https://www.tiktok.com/upload", "tiktok")
    assert matches_platform("https://business.facebook.com/latest/composer", "facebook")
    for url in ("https://tiktok.com.evil.test/upload", "https://facebook.com@evil.test/", "file://facebook.com/composer"):
        assert not matches_platform(url, "tiktok") and not matches_platform(url, "facebook")
    page = classify_page("https://business.facebook.com/latest/composer?asset_id=123&token=secret", {
        "controls": [{"label": "设置日期和时间", "disabled": False}, {"label": "发布", "disabled": True}],
        "file_inputs": 1, "enabled_file_inputs": 0,
    }, 1)
    assert page["composer_observed"] and page["identity"]["page_id_candidate"] == "123"
    assert "token" not in page["url"] and "secret" not in str(page)
    assert page["capabilities"]["schedule"]["state"] == "OBSERVED"
    assert page["capabilities"]["submit"]["state"] == "OBSERVED_DISABLED"
    assert page["capabilities"]["upload"]["state"] == "OBSERVED_DISABLED"
    assert page["capabilities"]["cover"]["state"] == "NOT_OBSERVED"
    assert page["identity"]["state"] == "UNVERIFIED"


def test_readonly_scan_and_partial_failures() -> None:
    class Page:
        def __init__(self, url, data=None, fails=False):
            self.url = url
            self.data = data or {"controls": []}
            self.fails = fails
            self.reads = 0

        def locator(self, selector):
            assert selector == "html"
            return self

        def evaluate(self, code, timeout):
            assert timeout == 4000
            self.reads += 1
            if self.fails:
                raise RuntimeError("private connection detail must not be stored")
            return self.data

    other = Page("https://facebook.com/")
    feed = Page("https://tiktok.com/@someone", {"controls": [{"label": "Upload"}]})
    tab = Page("https://tiktok.com/tiktokstudio/upload", {"controls": [{"label": "Edit cover"}, {"label": "Schedule"}], "file_inputs": 1, "enabled_file_inputs": 1})
    context = SimpleNamespace(pages=[other, feed, tab])
    result = inspect_context(context, "tiktok")
    assert result["status"] == "ENTRY_OBSERVED" and other.reads == 0
    assert result["capabilities"]["cover"] == "OBSERVED"
    assert not result["identity_verified"] and not result["automation_verified"]
    assert inspect_context(SimpleNamespace(pages=[tab, tab]), "tiktok")["status"] == "AMBIGUOUS_ENTRIES"
    context.pages.append(Page("https://tiktok.com/upload", fails=True))
    result = inspect_context(context, "tiktok")
    assert result["status"] == "PARTIAL_SCAN" and "private connection" not in str(result)
    assert inspect_context(SimpleNamespace(pages=[feed]), "tiktok")["status"] == "ENTRY_NOT_OPEN"
    assert inspect_context(SimpleNamespace(pages=[other]), "tiktok")["status"] == "NO_PLATFORM_TAB"
    verification = Page("https://tiktok.com/upload", {"alerts": ["VERIFICATION_PROMPT"]})
    assert inspect_context(SimpleNamespace(pages=[verification]), "tiktok")["status"] == "ACCOUNT_ACTION_REQUIRED"
    assert inspect_context(SimpleNamespace(pages=[Page("https://tiktok.com/upload", fails=True)]), "tiktok")["status"] == "SCAN_FAILED"
    assert inspect_context(SimpleNamespace(pages=[tab] * 11), "tiktok")["errors"][-1]["error_type"] == "TAB_LIMIT"


def test_record_binding() -> None:
    with tempfile.TemporaryDirectory() as directory:
        plan = Path(directory) / "publish_plan.csv"
        task = {"publish_id": "../../evil", "platform": "facebook", "account_key": "one", "profile_id": "001"}
        path = report_path(plan, task)
        assert path.parent == plan.parent / "entry_checks"
        save_report(path, {"status": "ENTRY_OBSERVED"})
        assert load_report(path)["status"] == "ENTRY_OBSERVED"
        for key in ("profile_id", "account_key", "platform", "composer_url", "facebook_content_mode"):
            changed = {**task, key: "changed"}
            assert report_path(plan, changed) != path
            assert load_report(report_path(plan, changed)) == {}
        path.write_text("broken JSON", encoding="utf-8")
        assert load_report(path) == {}


def test_background_check_preserves_plan_and_account() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        plan = root / "publish_plan.csv"
        ledger = root / "accounts.csv"
        write_csv(plan, ["publish_id", "platform", "status", "account_key", "browser_profile_id"], [
            {"publish_id": "T1", "platform": "tiktok", "status": "READY", "account_key": "tk1", "browser_profile_id": "001"},
        ])
        write_csv(ledger, ["account_key", "platform", "profile_id"], [
            {"account_key": "tk1", "platform": "tiktok", "profile_id": "001"},
        ])
        config = WorkbenchConfig(plan, root / "log.jsonl", root / "summary.csv", root / "detail.csv", root / "overview.csv",
                                 root / "report.html", root / "health.csv", ledger, "http://127.0.0.1:1", "tester")
        state = WorkbenchState(config)
        before = plan.read_bytes()
        started = threading.Event()
        released = threading.Event()
        pw = Mock()
        client = Mock()
        client.open_profile.return_value = SimpleNamespace(cdp_url="ws://local")

        def fake_inspect(context, platform):
            started.set()
            if not released.wait(5):
                raise RuntimeError("test did not release")
            return {"status": "ENTRY_OBSERVED", "checked_at": "test", "identity_verified": False, "automation_verified": False}

        try:
            with patch("rpa_workbench_server.BitBrowserClient", return_value=client), \
                 patch("rpa_workbench_server.connect_browser_context", return_value=(pw, Mock(), object())), \
                 patch("rpa_workbench_server.inspect_context", side_effect=fake_inspect):
                state.inspect_entry({"publish_id": "T1", "profile_id": "002", "platform": "facebook"})
                assert started.wait(2)
                assert state.snapshot()["inspection"]["running"]
                for action in (lambda: state.inspect_entry({"publish_id": "T1"}),
                               lambda: state.prepare_tasks({"publish_ids": ["T1"]}),
                               lambda: state.assign_account({"publish_id": "T1", "account_key": "tk1"}),
                               state.refresh_delivery):
                    try:
                        action()
                    except WorkbenchError:
                        pass
                    else:
                        raise AssertionError("mutation was allowed during entry inspection")
                released.set()
                state._inspection_thread.join(5)
                client.open_profile.assert_called_once_with("001")
                pw.stop.assert_called_once()
            assert plan.read_bytes() == before and not state.config.log_jsonl.exists()
            assert not state.inspection_status()["running"]
            assert state.find_task("T1")["entry_check"]["status"] == "ENTRY_OBSERVED"
            assert WorkbenchState(config).find_task("T1")["entry_check"]["status"] == "ENTRY_OBSERVED"
            with patch("rpa_workbench_server.BitBrowserClient", side_effect=RuntimeError("secret")):
                state.inspect_entry({"publish_id": "T1"})
                state._inspection_thread.join(5)
            assert state.find_task("T1")["entry_check"]["status"] == "CHECK_FAILED"
            assert "secret" not in str(state.inspection_status())
            assert plan.read_bytes() == before
        finally:
            released.set()
            if hasattr(state, "_inspection_thread"):
                state._inspection_thread.join(5)


def main() -> int:
    for test in (test_platform_and_capability_evidence, test_readonly_scan_and_partial_failures,
                 test_record_binding, test_background_check_preserves_plan_and_account):
        test()
        print("PASS " + test.__name__)
    print("Entry inspection self-test passed: 4 groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
