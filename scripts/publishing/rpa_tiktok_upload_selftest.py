"""Check TikTok entry fallback before upload, including real local browser DOM."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rpa_tiktok_upload import (
    TIKTOK_VIDEO_UPLOAD_URLS, TikTokUploadEntryError, attach_tiktok_video,
    open_tiktok_video_upload, read_upload_state,
)


class EntryPage:
    def __init__(self, states, statuses=None, failure=None):
        self.url = "about:blank"
        self.states = states
        self.statuses = statuses or [200] * len(states)
        self.failure = failure
        self.visited = []
        self.files = []

    def goto(self, url, **kwargs):
        self.visited.append(url)
        self.url = url
        if self.failure:
            raise self.failure
        return SimpleNamespace(status=self.statuses[len(self.visited) - 1])

    def state(self, page=None):
        state = self.states[len(self.visited) - 1]
        return {"state": state, "input_index": 1} if state == "READY" else {"state": state}

    def wait_for_function(self, *args, **kwargs):
        raise TimeoutError("local fixture: no uploader appeared")

    def locator(self, selector):
        assert selector == "input[type='file']"
        return self

    def nth(self, index):
        assert index == 1
        return self

    def set_input_files(self, path, timeout):
        self.files.append(path)


def test_entry_fallbacks_and_single_attachment():
    for states, count in ((["READY"], 1), (["WAITING", "READY"], 2), (["WRONG_PAGE", "WAITING", "READY"], 3)):
        page = EntryPage(states)
        with patch("rpa_tiktok_upload.read_upload_state", side_effect=page.state):
            result = open_tiktok_video_upload(page, ready_timeout_ms=1)
            attach_tiktok_video(page, Path("chosen-second-video.mp4"), result, 100)
        assert page.visited == list(TIKTOK_VIDEO_UPLOAD_URLS[:count])
        assert result["requested_url"] == TIKTOK_VIDEO_UPLOAD_URLS[count - 1]
        assert page.files == ["chosen-second-video.mp4"]
        assert len(result["attempts"]) == count


def test_blocked_entries_do_not_try_other_routes():
    for code in ("LOGIN_REQUIRED", "ACCOUNT_VERIFICATION", "PLATFORM_RATE_LIMIT_OR_RESTRICTION", "TIKTOK_UPLOAD_DRAFT_PRESENT", "TIKTOK_UPLOAD_INPUT_AMBIGUOUS"):
        page = EntryPage([code])
        with patch("rpa_tiktok_upload.read_upload_state", side_effect=page.state):
            try:
                open_tiktok_video_upload(page)
            except TikTokUploadEntryError as exc:
                assert exc.code == code and len(exc.attempts) == 1
            else:
                raise AssertionError("Blocked entry was accepted")
        assert len(page.visited) == 1 and not page.files
    for status in (401, 403, 429):
        page = EntryPage(["WAITING"], [status])
        try:
            open_tiktok_video_upload(page)
        except TikTokUploadEntryError:
            pass
        else:
            raise AssertionError("HTTP login/access restriction accepted")
        assert len(page.visited) == 1
    page = EntryPage(["WAITING"], failure=RuntimeError("net::ERR_PROXY_CONNECTION_FAILED"))
    try:
        open_tiktok_video_upload(page)
    except RuntimeError as exc:
        assert "ERR_PROXY" in str(exc)
    else:
        raise AssertionError("Proxy error was ignored")
    assert len(page.visited) == 1


def test_upload_failure_cannot_navigate_again():
    from bitbrowser_rpa_example import publish_tiktok, classify_error, recommend_error_action

    page = EntryPage(["READY"])
    with patch("rpa_tiktok_upload.read_upload_state", side_effect=page.state), \
         patch.object(page, "set_input_files", side_effect=TimeoutError("outcome unknown")), \
         patch("bitbrowser_rpa_example.fill_text_best_effort") as caption:
        try:
            publish_tiktok(page, Path("second.mp4"), "Second caption")
        except TimeoutError:
            pass
        else:
            raise AssertionError("Upload uncertainty was hidden")
        caption.assert_not_called()
    assert page.visited == [TIKTOK_VIDEO_UPLOAD_URLS[0]]
    page = EntryPage(["WAITING"] * 3)
    with patch("rpa_tiktok_upload.read_upload_state", side_effect=page.state):
        try:
            open_tiktok_video_upload(page, ready_timeout_ms=1)
        except TikTokUploadEntryError as exc:
            assert exc.code == "TIKTOK_UPLOAD_ENTRY_UNAVAILABLE"
            assert len(exc.attempts) == 3
            assert classify_error(type(exc).__name__, str(exc), "tiktok") == exc.code
            assert recommend_error_action(exc.code, "FAILED") == "RETRY_OR_MANUAL_CHECK"
        else:
            raise AssertionError("Missing uploader accepted")


def run_browser_checks(browser):
    """Fulfill all platform URLs locally; no network or account is used."""
    with tempfile.TemporaryDirectory() as directory:
        media = Path(directory) / "local.mp4"
        media.write_bytes(b"local fixture")
        html = '<input type="file" accept="image/*"><input type="file" accept="video/mp4" hidden>'

        def run_case(first, second=html, third=html, expected=1):
            context = browser.new_context()
            visited = []

            def route(request):
                url = request.request.url
                visited.append(url)
                index = TIKTOK_VIDEO_UPLOAD_URLS.index(url)
                response = (first, second, third)[index]
                if isinstance(response, dict):
                    request.fulfill(**response)
                else:
                    request.fulfill(status=200, content_type="text/html", body=response)

            context.route("**/*", route)
            page = context.new_page()
            try:
                result = open_tiktok_video_upload(page, ready_timeout_ms=250)
                assert result["input_index"] == 1
                assert result["requested_url"] == TIKTOK_VIDEO_UPLOAD_URLS[expected - 1]
                assert [url for url in visited if url in TIKTOK_VIDEO_UPLOAD_URLS] == list(TIKTOK_VIDEO_UPLOAD_URLS[:expected])
                attach_tiktok_video(page, media, result, 1000)
                assert page.locator('input[type="file"]').nth(0).evaluate("el => el.files.length") == 0
                assert page.locator('input[type="file"]').nth(1).evaluate("el => el.files[0].name") == "local.mp4"
                assert read_upload_state(page)["state"] == "TIKTOK_UPLOAD_DRAFT_PRESENT"
                try:
                    open_tiktok_video_upload(page)
                except TikTokUploadEntryError as exc:
                    assert exc.code == "TIKTOK_UPLOAD_DRAFT_PRESENT"
                else:
                    raise AssertionError("Existing upload was replaced by navigation")
            finally:
                context.close()

        run_case(html)
        run_case('<input type="file" accept="image/*">', expected=2)
        run_case({"status": 404, "body": "Unavailable"}, '<input type="file" accept="video/*" disabled>', expected=3)
        run_case('<input type="file" accept="image/*"><script>setTimeout(() => { const i=document.createElement("input"); i.type="file"; i.accept="video/*"; document.body.append(i); }, 60);</script>')
        # Photo mode, login and verification must not be confused with a ready video input.
        context = browser.new_context()
        context.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
        page = context.new_page()
        try:
            for url, expected in (
                ("https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=photo", "WRONG_MEDIA_TAB"),
                ("https://www.tiktok.com/login", "LOGIN_REQUIRED"),
                ("https://www.tiktok.com/verify", "ACCOUNT_VERIFICATION"),
                ("https://www.tiktok.com.evil.test/tiktokstudio/upload", "UNEXPECTED_ORIGIN"),
            ):
                page.goto(url)
                assert read_upload_state(page)["state"] == expected
            page.goto(TIKTOK_VIDEO_UPLOAD_URLS[0])
            page.set_content('<input type="file" accept="video/mp4"><input type="file" accept="video/webm">')
            assert read_upload_state(page)["state"] == "TIKTOK_UPLOAD_INPUT_AMBIGUOUS"
            page.set_content('<input type="file" accept="video/mp4"><div>Log in to upload</div>')
            assert read_upload_state(page)["state"] == "LOGIN_REQUIRED"
            page.set_content('<input type="file" accept="video/mp4"><div>Verify you are human</div>')
            assert read_upload_state(page)["state"] == "ACCOUNT_VERIFICATION"
        finally:
            context.close()
    print("PASS TikTok Studio webapp/creator_center/legacy routes, delayed controls, video-only attachment and draft protection (local browser)")


def main():
    for test in (test_entry_fallbacks_and_single_attachment, test_blocked_entries_do_not_try_other_routes,
                 test_upload_failure_cannot_navigate_again):
        test()
        print("PASS " + test.__name__)
    print("TikTok upload entry self-test passed: 3 groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
