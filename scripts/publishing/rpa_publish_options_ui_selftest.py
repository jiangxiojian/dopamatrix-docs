"""Exercise cover presets and content review using only a local workbench."""

from __future__ import annotations

import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from rpa_operator_console_selftest import write_csv
from rpa_publish_options import hash_file
from rpa_publish_options_selftest import make_state, png_bytes
from rpa_workbench_server import WorkbenchHandler


def main() -> int:
    screenshots = Path(__file__).resolve().parent / "build" / "workbench-ui-check"
    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        state, copy = make_state(root)
        image = root / "outside-cover.png"
        image.write_bytes(png_bytes())

        class Handler(WorkbenchHandler):
            def log_message(self, *args):
                pass

        Handler.state = state
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        released = threading.Event()

        def delayed_hash(path):
            if not released.wait(20):
                raise RuntimeError("confirmation UI test was not released")
            return hash_file(path)

        try:
            with patch("rpa_workbench_server.publisher_main") as publisher, sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 850})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(base)
                article = page.locator('article[data-id="T1"]')
                article.locator('summary').click()
                article.locator('[data-option="publish_mode"]').select_option('platform_schedule')
                article.locator('[data-option="publish_time"]').fill('2099-06-01T12:00')
                article.locator('[data-option="timezone"]').select_option('Asia/Shanghai')
                article.locator('[data-cover-upload]').set_input_files(str(image))
                article.locator('.cover-preview').wait_for(state='visible')
                page.wait_for_function("document.querySelector('[data-cover-preview=\"T1\"]').naturalWidth === 80")
                article.locator('[data-action="save-options"]').click()
                page.wait_for_function("document.querySelector('[data-confirmation-result=\"T1\"]').parentElement.textContent.includes('2099-06-01T04:00:00+00:00')")
                assert '尚未提交平台排期' in article.inner_text()
                task = state.find_task('T1')
                assert task['publication']['options']['cover_path'].startswith('covers/')
                assert state.config.plan_csv.read_bytes().find(b'2099') == -1  # Preset only; no fake scheduled result.
                assert len(list((root / 'covers').glob('*.png'))) == 1
                article.locator('[data-select]').check()
                page.locator('#confirmSelected').click()
                page.locator('#reviewDialog').wait_for(state='visible')
                assert 'Caption 1' in page.locator('#reviewItems').inner_text()
                assert '2099-06-01T12:00' in page.locator('#reviewItems').inner_text()
                page.screenshot(path=str(screenshots / 'content-review-preview.png'), full_page=True)
                page.locator('#reviewOperator').fill('Alice')
                with patch('rpa_publish_options.hash_file', side_effect=delayed_hash):
                    page.locator('#saveReview').click()
                    page.wait_for_function("document.querySelector('#confirmation').textContent.includes('正在计算')")
                    assert page.locator('#prepareSelected').is_disabled()
                    assert article.locator('[data-action="save-options"]').is_disabled()
                    page.reload()
                    page.wait_for_function("document.querySelector('#confirmation').textContent.includes('正在计算')")
                    released.set()
                    page.wait_for_function("document.querySelector('#confirmation').textContent.includes('已记录 1 条')")
                article.locator('summary').click()
                assert '内容已确认，尚未自动提交' in article.locator('[data-confirmation-result]').inner_text()
                assert state.find_task('T1')['status'] == 'READY'
                assert 'Alice' in article.locator('[data-confirmation-result]').inner_text()
                page.reload()
                article.locator('summary').click()
                assert article.locator('[data-option="publish_mode"]').input_value() == 'platform_schedule'
                assert article.locator('[data-option="timezone"]').input_value() == 'Asia/Shanghai'
                assert article.locator('.cover-preview').is_visible()
                page.screenshot(path=str(screenshots / 'publishing-options-desktop.png'), full_page=True)

                # The latest source is checked without reopening the launcher or web server.
                copy[0]['情绪化描述'] = 'New caption, saved after confirmation'
                write_csv(root / '矩阵投放文案对照表.csv', list(copy[0]), copy)
                page.reload()
                article.locator('summary').click()
                assert '内容已变化，需要重新确认' in article.locator('[data-confirmation-result]').inner_text()
                assert '文案表已变化' in article.inner_text()
                page.locator('#reload').click()
                page.wait_for_function("document.querySelector('article[data-id=\"T1\"]').textContent.includes('New caption, saved after confirmation')")
                article.locator('[data-select]').check()
                page.locator('#confirmSelected').click()
                assert 'New caption, saved after confirmation' in page.locator('#reviewItems').inner_text()
                page.locator('#reviewOperator').fill('Bob')
                page.locator('#saveReview').click()
                page.wait_for_function("document.querySelector('[data-confirmation-result=\"T1\"]').textContent.includes('Bob')")
                assert state.options_store.verify_confirmation(state.find_task('T1'))
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile horizontal overflow'
                page.screenshot(path=str(screenshots / 'publishing-options-mobile.png'), full_page=True)
                assert not errors, errors
                publisher.assert_not_called()
                browser.close()
        finally:
            released.set()
            if hasattr(state, '_confirmation_thread'):
                state._confirmation_thread.join(5)
            server.shutdown()
            server.server_close()
            thread.join(5)
    print('PASS cover import/preview, publishing presets, content preview, confirmation recovery, stale content and mobile layout')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
