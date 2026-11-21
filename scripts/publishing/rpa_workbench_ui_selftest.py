"""Exercise launcher validation and the workbench UI without contacting platforms."""

from __future__ import annotations

import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from playwright.sync_api import sync_playwright

from bitbrowser_rpa_example import DEFAULT_ACCOUNT_LEDGER_FILENAME, update_publish_plan_row
from dopa_matrix_publisher import LedgerEditorWindow, PublisherLauncher
from rpa_operator_console_selftest import write_csv
from rpa_workbench_server import WorkbenchConfig, WorkbenchHandler, WorkbenchState
from rpa_entry_check import CONTROL_SNAPSHOT_JS, classify_page
import rpa_publish_options_ui_selftest
import rpa_tiktok_upload_selftest


def main() -> int:
    screenshot_dir = Path(__file__).resolve().parent / "build" / "workbench-ui-check"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "videos").mkdir()
        (root / "videos" / "demo.mp4").write_bytes(b"offline-ui-test")
        source = root / "矩阵投放文案对照表.csv"
        write_csv(source, ["视频文件名", "情绪化描述", "黄金标签"], [{"视频文件名": "demo.mp4", "情绪化描述": "Initial caption", "黄金标签": "#Initial"}])
        plan = root / "publish_plan.csv"
        ledger = root / DEFAULT_ACCOUNT_LEDGER_FILENAME
        write_csv(plan, ["publish_id", "platform", "account_key", "browser_profile_id", "media_path", "status"], [
            {"publish_id": "T1", "platform": "tiktok", "account_key": "tk1", "browser_profile_id": "profile-1", "media_path": "videos/demo.mp4", "status": "READY"},
            {"publish_id": "F1", "platform": "facebook", "account_key": "fb1", "browser_profile_id": "profile-1", "media_path": "videos/demo.mp4", "status": "READY"},
        ])
        accounts = [
            {"account_key": "tk1", "platform": "tiktok", "profile_id": "profile-1", "profile_name": "Shared TK + FB"},
            {"account_key": "tk2", "platform": "tiktok", "profile_id": "profile-2", "profile_name": "Second window"},
            {"account_key": "fb1", "platform": "facebook", "profile_id": "profile-1", "profile_name": "Shared TK + FB"},
        ]
        launcher = PublisherLauncher()
        launcher.withdraw()
        try:
            try:
                launcher.validate_package(False)
            except ValueError:
                pass
            else:
                raise AssertionError("empty folder selection silently resolved to cwd")
            launcher.delivery_dir.set(str(root))
            launcher.refresh_package_check()
            assert "缺少 " + DEFAULT_ACCOUNT_LEDGER_FILENAME in launcher.package_check.get()
            editor = LedgerEditorWindow(launcher, root, ledger, "http://127.0.0.1:1")
            editor.withdraw()
            editor.rows = accounts
            editor.refresh_tree(select_first=True)
            with patch("dopa_matrix_publisher.messagebox.showinfo"):
                editor.save_ledger()
            assert "找到" + " " + DEFAULT_ACCOUNT_LEDGER_FILENAME in launcher.package_check.get()
            assert "投放包检查通过" in launcher.status.get(), ascii(launcher.package_check.get())
            editor.destroy()
        finally:
            launcher.destroy()
        print("PASS launcher save refreshes package validation without reselecting the folder")

        state = WorkbenchState(WorkbenchConfig(
            plan_csv=plan, log_jsonl=root / "log.jsonl", summary_csv=root / "summary.csv",
            customer_report_detail_csv=root / "detail.csv", customer_report_overview_csv=root / "overview.csv",
            customer_report_html=root / "report.html", account_health_csv=root / "health.csv",
            account_ledger_csv=ledger, bit_api="http://127.0.0.1:1", operator="test",
        ))

        class Handler(WorkbenchHandler):
            def log_message(self, *args):
                pass

        Handler.state = state
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        released = threading.Event()
        inspection_released = threading.Event()
        calls = []

        def fake_publisher(argv, progress_callback=None):
            calls.append(argv)
            progress_callback({"publish_id": "T1", "index": 1, "total": 1, "message": "正在上传 TikTok 视频"})
            if not released.wait(20):
                raise RuntimeError("UI test release timed out")
            update_publish_plan_row(plan, "T1", {"status": "PREPARED"})
            return 0

        def fake_inspect(context, platform):
            if not inspection_released.wait(20):
                raise RuntimeError("Entry inspection UI test release timed out")
            return {"status": "ENTRY_OBSERVED", "checked_at": "2026-11-20T15:00:00+08:00", "tabs": [],
                    "identity_verified": False, "automation_verified": False,
                    "capabilities": {"schedule": "OBSERVED", "cover": "NOT_OBSERVED"}}

        try:
            with patch("rpa_workbench_server.publisher_main", fake_publisher), sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                rpa_tiktok_upload_selftest.run_browser_checks(browser)
                fixture = browser.new_page()
                fixture.set_content('''<button disabled>Post</button><button style="display:none">Edit cover</button>
                    <input type="checkbox" role="switch" aria-label="设置日期和时间">
                    <input type="file" hidden><input type="text" role="spinbutton" aria-label="小时">
                    <script>window.actions = 0; document.addEventListener('click', () => window.actions++);</script>''')
                controls = fixture.locator('html').evaluate(CONTROL_SNAPSHOT_JS)
                observed = classify_page('https://business.facebook.com/latest/composer', controls, 1)
                assert observed['capabilities']['schedule']['state'] == 'OBSERVED'
                assert observed['capabilities']['submit']['state'] == 'OBSERVED_DISABLED'
                assert observed['capabilities']['cover']['state'] == 'NOT_OBSERVED'
                assert observed['capabilities']['upload']['state'] == 'OBSERVED'
                assert any(control.get('role') == 'spinbutton' for control in controls['controls'])
                assert fixture.evaluate('window.actions') == 0
                assert not fixture.get_by_role('switch').is_checked()
                fixture.close()
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base_url = f"http://127.0.0.1:{server.server_port}"
                page.goto(base_url)
                page.locator('[data-assignment="T1"]').wait_for()
                assert page.locator('[data-assignment="T1"] option').all_text_contents() == [
                    "请选择目标账号", "tk1 · Shared TK + FB", "tk2 · Second window",
                ]
                page.locator('[data-assignment="T1"]').select_option("tk2")
                assert "profile-2（待保存）" in page.locator('[data-window="T1"]').inner_text()
                page.locator('[data-action="assign"][data-id="T1"]').click()
                page.wait_for_function("document.querySelector('[data-window=\"T1\"]').textContent.includes('profile-2') && !document.querySelector('[data-window=\"T1\"]').textContent.includes('待保存')")
                assert state.find_task("T1")["profile_id"] == "profile-2"
                page.screenshot(path=str(screenshot_dir / "desktop.png"), full_page=True)
                write_csv(source, ["视频文件名", "情绪化描述", "黄金标签"], [{"视频文件名": "demo.mp4", "情绪化描述": "Edited after page opened", "黄金标签": "#Updated"}])
                page.locator('[data-select="T1"]').check()
                page.locator('#prepareSelected').click()
                page.wait_for_function("document.querySelector('#preparation').textContent.includes('正在上传 TikTok 视频')")
                assert page.locator('#prepareSelected').is_disabled()
                assert page.locator('[data-action="assign"][data-id="T1"]').is_disabled()
                assert len(calls) == 1
                assert state.find_task("T1")["caption"] == "Edited after page opened"
                assert state.find_task("T1")["hashtags"] == "#Updated"
                page.reload()
                page.wait_for_function("document.querySelector('#preparation').textContent.includes('正在上传 TikTok 视频')")
                assert page.locator('#prepareSelected').is_disabled()
                page.screenshot(path=str(screenshot_dir / "running.png"), full_page=True)
                released.set()
                page.wait_for_function("document.querySelector('#preparation').textContent.includes('草稿就绪 1 条')")
                page.wait_for_function("!document.querySelector('#prepareSelected').disabled")
                assert page.locator('[data-select="T1"]').is_disabled()
                # Add a delivery row after the page is open, without reopening the launcher or page.
                (root / "videos" / "second.mp4").write_bytes(b"offline-ui-test")
                write_csv(source, ["视频文件名", "情绪化描述", "黄金标签"], [
                    {"视频文件名": "demo.mp4", "情绪化描述": "Edited after page opened", "黄金标签": "#Updated"},
                    {"视频文件名": "second.mp4", "情绪化描述": "Second video caption", "黄金标签": "#Second"},
                ])
                page.locator('#reload').click()
                page.wait_for_function("document.querySelector('#listHint').textContent.includes('4 / 4')")
                assert "新增 2 条任务" in page.locator('#deliverySync').inner_text()  # Existing plan targets TK + FB video.
                assert state.find_task("T1")["status"] == "PREPARED"
                page.locator('#reload').click()
                page.wait_for_function("document.querySelector('#deliverySync').textContent.includes('新增 0 条任务')")
                assert len(state.snapshot()["tasks"]) == 4
                with source.open("a", encoding="utf-8", newline="") as fh:
                    fh.write('missing.mp4,Missing file caption,#Missing\n')
                page.locator('#reload').click()
                page.locator('#deliverySync').get_by_text('未新增任务，缺少素材文件：missing.mp4', exact=False).wait_for()
                page.screenshot(path=str(screenshot_dir / "delivery-refresh.png"), full_page=True)
                fake_client = Mock()
                fake_client.open_profile.return_value = SimpleNamespace(cdp_url='ws://fixture')
                with patch('rpa_workbench_server.BitBrowserClient', return_value=fake_client), \
                     patch('rpa_workbench_server.connect_browser_context', return_value=(Mock(), Mock(), object())), \
                     patch('rpa_workbench_server.inspect_context', side_effect=fake_inspect):
                    page.locator('article[data-id="T1"] summary').click()
                    page.locator('[data-action="inspect"][data-id="T1"]').click()
                    page.wait_for_function("document.querySelector('#inspection').textContent.includes('正在读取')")
                    assert page.locator('#prepareSelected').is_disabled()
                    assert page.locator('[data-action="inspect"][data-id="T1"]').is_disabled()
                    page.reload()
                    page.wait_for_function("document.querySelector('#inspection').textContent.includes('正在读取')")
                    page.locator('article[data-id="T1"] summary').click()
                    inspection_released.set()
                    page.locator('[data-entry-result="T1"]').wait_for()
                    assert '定时：发现入口，未验证' in page.locator('[data-entry-result="T1"]').inner_text()
                    assert page.locator('article[data-id="T1"] details').get_attribute('open') is not None
                    assert state.find_task('T1')['status'] == 'PREPARED'
                    fake_client.open_profile.assert_called_once_with('profile-2')
                report_link = page.locator('[data-entry-result="T1"] a').get_attribute('href')
                assert page.request.get(base_url + report_link).status == 200
                page.reload()
                page.locator('article[data-id="T1"] summary').click()
                page.locator('[data-entry-result="T1"]').wait_for()
                page.screenshot(path=str(screenshot_dir / 'entry-check.png'), full_page=True)
                with patch('rpa_workbench_server.BitBrowserClient', side_effect=RuntimeError('offline')):
                    page.locator('[data-action="inspect"][data-id="T1"]').click()
                    page.wait_for_function("document.querySelector('[data-entry-result=\"T1\"]').textContent.includes('入口检查失败')")
                    assert page.locator('#prepareSelected').is_enabled()
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "mobile horizontal overflow"
                page.screenshot(path=str(screenshot_dir / "mobile.png"), full_page=True)
                assert not errors, errors
                assert len(calls) == 1
                browser.close()
        finally:
            released.set()
            inspection_released.set()
            if hasattr(state, "_prepare_thread"):
                state._prepare_thread.join(5)
            if hasattr(state, "_inspection_thread"):
                state._inspection_thread.join(5)
            server.shutdown()
            server.server_close()
            thread.join(5)
    print("PASS browser account assignment, progress, delivery refresh, entry checks, duplicate protection and mobile layout")
    print(f"Screenshots: {screenshot_dir}")
    rpa_publish_options_ui_selftest.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
