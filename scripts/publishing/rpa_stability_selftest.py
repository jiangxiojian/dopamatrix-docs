"""Self-test popup handling and error classification helpers."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bitbrowser_rpa_example import (  # noqa: E402
    BitBrowserError,
    classify_error,
    classify_partial_result,
    describe_error_action,
    dismiss_safe_popups,
    handle_content_check_popup,
    recommend_error_action,
)


def assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


class _FakeLocator:
    def __init__(self, counts: dict[str, int], clicks: list[tuple[str, int]], label: str) -> None:
        self._counts = counts
        self._clicks = clicks
        self._label = label

    @property
    def first(self) -> "_FakeLocator":
        return self

    def count(self) -> int:
        return self._counts.get(self._label, 0)

    def click(self, timeout: int = 0) -> None:
        self._clicks.append((self._label, timeout))
        self._counts[self._label] = 0


class _FakeTextLocator:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class _FakeContentCheckPage:
    def __init__(self, present: bool = True) -> None:
        self.present = present
        self.clicked: list[str] = []
        self.waits: list[int] = []

    def get_by_text(self, text: str, exact: bool = False) -> _FakeTextLocator:
        return _FakeTextLocator(1 if self.present and exact else 0)

    def get_by_role(self, role: str, name: str):
        class _RoleLocator:
            def __init__(self, clicked: list[str], button_name: str) -> None:
                self._clicked = clicked
                self._button_name = button_name

            def click(self, timeout: int = 0) -> None:
                self._clicked.append(self._button_name)

        return _RoleLocator(self.clicked, name)

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakePopupPage:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts
        self.clicks: list[tuple[str, int]] = []
        self.waits: list[int] = []

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self.counts, self.clicks, selector)

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


def test_popup_dismissal() -> None:
    page = _FakePopupPage(
        {
            "button:has-text('Cancel')": 1,
            "button:has-text('Maybe later')": 1,
        }
    )
    clicked = dismiss_safe_popups(page)
    assert_equal(
        clicked,
        ["button:has-text('Maybe later')"],
        "Dismiss safe popup buttons",
    )
    assert_equal(page.waits, [1000], "Wait between popup clicks")


def test_content_check_popup() -> None:
    page = _FakeContentCheckPage(present=True)
    try:
        handle_content_check_popup(page, "pause")
    except BitBrowserError as exc:
        assert_equal("content checks" in str(exc).lower(), True, "Pause raises for content check popup")
    else:
        raise AssertionError("Pause should raise when the content check popup is present")

    enable_page = _FakeContentCheckPage(present=True)
    enable_result = handle_content_check_popup(enable_page, "enable")
    assert_equal(enable_result, {"detected": True, "action": "enable"}, "Enable content check popup")
    assert_equal(enable_page.clicked, ["Turn on"], "Enable button click")

    cancel_page = _FakeContentCheckPage(present=True)
    cancel_result = handle_content_check_popup(cancel_page, "cancel")
    assert_equal(cancel_result, {"detected": True, "action": "cancel"}, "Cancel content check popup")
    assert_equal(cancel_page.clicked, ["Cancel"], "Cancel button click")


def test_error_classification() -> None:
    assert_equal(
        classify_error("TimeoutError", "Hard timeout waiting for task", "tiktok"),
        "TASK_TIMEOUT",
        "Task timeout classification",
    )
    assert_equal(
        classify_error("PlaywrightError", "File chooser timed out while uploading", "facebook"),
        "FACEBOOK_FILE_CHOOSER_TIMEOUT",
        "Facebook file chooser timeout",
    )
    assert_equal(
        classify_error("Error", "Turn on automatic content checks?", "tiktok"),
        "TIKTOK_CONTENT_CHECK_SETTING",
        "TikTok content check classification",
    )
    assert_equal(
        classify_error("Error", "face verification required", "facebook"),
        "ACCOUNT_VERIFICATION",
        "Account verification classification",
    )
    assert_equal(
        classify_error("Error", "Page permission denied", "facebook"),
        "FACEBOOK_PAGE_ACCESS",
        "Facebook page access classification",
    )


def test_error_action_recommendation() -> None:
    assert_equal(
        recommend_error_action("PROXY_CONNECTION_FAILED", "FAILED"),
        "CHECK_PROXY",
        "Proxy failure action",
    )
    assert_equal(
        recommend_error_action("ACCOUNT_VERIFICATION", "FAILED"),
        "HUMAN_ACCOUNT_CHECK",
        "Account verification action",
    )
    assert_equal(
        recommend_error_action("FACEBOOK_FILE_CHOOSER_TIMEOUT", "FAILED"),
        "RETRY_OR_MANUAL_CHECK",
        "File chooser timeout action",
    )
    assert_equal(
        recommend_error_action("POST_URL_NOT_FOUND", "PREPARED"),
        "RETRY_OR_MANUAL_CHECK",
        "Post URL not found action",
    )
    assert_equal(
        describe_error_action("CHECK_PROXY"),
        "检查代理 (CHECK_PROXY)",
        "Error action label",
    )
    assert_equal(
        recommend_error_action("", "PREPARED"),
        "HUMAN_PUBLISH_CHECK",
        "Prepared draft action",
    )
    assert_equal(
        recommend_error_action("", "PUBLISHED_MANUAL"),
        "DONE",
        "Published action",
    )


def test_partial_result_classification() -> None:
    assert_equal(
        classify_partial_result({"platform": "tiktok", "uploaded": False}),
        ("TIKTOK_UPLOAD_NOT_CONFIRMED", "TikTok media upload was not confirmed by the page."),
        "TikTok partial upload result",
    )
    assert_equal(
        classify_partial_result({"platform": "facebook", "uploaded": True, "caption_filled": False}),
        ("FACEBOOK_CAPTION_NOT_FILLED", "Facebook post text field was not filled."),
        "Facebook partial caption result",
    )


def main() -> int:
    tests = [
        test_popup_dismissal,
        test_content_check_popup,
        test_error_classification,
        test_error_action_recommendation,
        test_partial_result_classification,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Popup and error stability self-test passed: {len(tests)} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
