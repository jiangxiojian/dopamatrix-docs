"""Self-test URL detection helpers used by the RPA publisher.

These checks do not open BitBrowser or connect to any platform. They protect the
small parsing and ranking rules that decide which published post URL should be
written back after an operator clicks Publish.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bitbrowser_rpa_example import (  # noqa: E402
    _facebook_candidate_time_delta_seconds,
    _post_candidate_sort_key,
    collect_post_url_candidates,
    extract_platform_post_id,
    facebook_business_content_candidate,
    normalize_post_url,
)


def assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_tiktok_post_ids() -> None:
    assert_equal(
        extract_platform_post_id("https://www.tiktok.com/@xiojian9527/video/7675641440810093844", "tiktok"),
        "7675641440810093844",
        "TikTok public video URL",
    )
    assert_equal(
        extract_platform_post_id("https://www.tiktok.com/tiktokstudio/content?item_id=7675641440810093844", "tiktok"),
        "7675641440810093844",
        "TikTok Studio item_id",
    )
    assert_equal(
        normalize_post_url(
            "https://www.tiktok.com/tiktokstudio/content?item_id=7675641440810093844&username=xiojian9527",
            "tiktok",
        ),
        "https://www.tiktok.com/@xiojian9527/video/7675641440810093844",
        "TikTok Studio public fallback URL",
    )
    assert_equal(
        extract_platform_post_id("https://www.tiktok.com/@xiojian9527/photo/7675641440810093844", "tiktok"),
        "7675641440810093844",
        "TikTok public photo URL",
    )
    assert_equal(
        normalize_post_url(
            "https://www.tiktok.com/player/v1/7675641440810093844?share=1&foo=bar",
            "tiktok",
        ),
        "https://www.tiktok.com/player/v1/7675641440810093844",
        "TikTok player fallback URL",
    )


def test_facebook_post_ids() -> None:
    assert_equal(
        extract_platform_post_id(
            "https://www.facebook.com/1237975296070200/posts/122106554229435838",
            "facebook",
        ),
        "122106554229435838",
        "Facebook posts URL",
    )
    assert_equal(
        normalize_post_url("https://business.facebook.com/latest/posts/published_posts/", "facebook"),
        "",
        "Ignore Facebook Business Suite navigation URL",
    )
    assert_equal(
        facebook_business_content_candidate(
            "https://business.facebook.com/latest/insights/object_insights/?content_id=122106554229435838&asset_id=1237975296070200"
        ),
        "https://www.facebook.com/1237975296070200/posts/122106554229435838",
        "Facebook Business Suite content_id candidate",
    )
    assert_equal(
        facebook_business_content_candidate(
            "https://business.facebook.com/latest/insights/object_insights/?content_id=122106554229435838",
            fallback_page_id="1237975296070200",
        ),
        "https://www.facebook.com/1237975296070200/posts/122106554229435838",
        "Facebook Business Suite fallback page id",
    )
    assert_equal(
        extract_platform_post_id("https://www.facebook.com/reel/122106554229435838", "facebook"),
        "122106554229435838",
        "Facebook reels URL",
    )
    assert_equal(
        extract_platform_post_id(
            "https://www.facebook.com/story.php?story_fbid=122106554229435838&id=1237975296070200",
            "facebook",
        ),
        "122106554229435838",
        "Facebook story.php URL",
    )
    assert_equal(
        normalize_post_url(
            "https://www.facebook.com/story.php?story_fbid=122106554229435838&id=1237975296070200&ref=sharing",
            "facebook",
        ),
        "https://www.facebook.com/permalink.php?story_fbid=122106554229435838&id=1237975296070200",
        "Facebook story.php canonical permalink",
    )
    assert_equal(
        normalize_post_url(
            "https://www.facebook.com/photo.php?fbid=122106554229435838&id=1237975296070200&set=a.1",
            "facebook",
        ),
        "https://www.facebook.com/photo.php?fbid=122106554229435838&id=1237975296070200",
        "Facebook photo.php canonical URL",
    )
    assert_equal(
        normalize_post_url(
            "https://www.facebook.com/watch?v=122106554229435838&ref=sharing",
            "facebook",
        ),
        "https://www.facebook.com/watch?v=122106554229435838",
        "Facebook watch URL",
    )
    assert_equal(
        extract_platform_post_id(
            "https://www.facebook.com/1237975296070200/photos/a.111/122106554229435838/?type=3",
            "facebook",
        ),
        "122106554229435838",
        "Facebook page photo path URL",
    )
    assert_equal(
        normalize_post_url(
            "https://www.facebook.com/1237975296070200/photos/a.111/122106554229435838/?type=3&ref=sharing",
            "facebook",
        ),
        "https://www.facebook.com/1237975296070200/photos/a.111/122106554229435838",
        "Facebook page photo path canonical URL",
    )


class FakePage:
    def __init__(self, url: str, items: list[dict[str, str]] | None = None, error: Exception | None = None) -> None:
        self.url = url
        self._items = items or []
        self._error = error

    def evaluate(self, script: str) -> list[dict[str, str]]:
        if self._error is not None:
            raise self._error
        return self._items


class FakeContext:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages


def test_facebook_embedded_url_candidates() -> None:
    page = FakePage(
        "https://business.facebook.com/latest/posts/published_posts/?asset_id=1237975296070200",
        [
            {
                "source": "text:facebook_public_url",
                "url": "https://www.facebook.com/1237975296070200/photos/a.111/122106554229435838/?type=3",
                "text": "16:08",
            },
            {
                "source": "text:facebook_business_content_id",
                "url": "https://business.facebook.com/latest/insights/object_insights/?content_id=122106554229435839&asset_id=1237975296070200",
                "text": "16:09",
            },
        ],
    )
    candidates = collect_post_url_candidates(page, "facebook", tab_index=2)
    urls = {item["post_url"] for item in candidates}
    assert_equal(
        "https://www.facebook.com/1237975296070200/photos/a.111/122106554229435838" in urls,
        True,
        "Collect embedded Facebook public photo URL",
    )
    assert_equal(
        "https://www.facebook.com/1237975296070200/posts/122106554229435839" in urls,
        True,
        "Collect embedded Facebook Business Suite content_id URL",
    )


def test_detection_diagnostics() -> None:
    from bitbrowser_rpa_example import detect_post_url_in_context

    detected_context = FakeContext(
        [
            FakePage("https://business.facebook.com/latest/composer"),
            FakePage(
                "https://business.facebook.com/latest/posts/published_posts/?asset_id=1237975296070200",
                [
                    {
                        "source": "text:facebook_business_content_id",
                        "url": "https://business.facebook.com/latest/insights/object_insights/?content_id=122106554229435839&asset_id=1237975296070200",
                        "text": "16:09",
                    }
                ],
            ),
        ]
    )
    detected = detect_post_url_in_context(detected_context, "facebook")
    assert_equal(detected["detected"], True, "Detected post URL")
    assert_equal(detected["candidate_count"], 1, "Detected candidate count")
    assert_equal(detected["scanned_tab_count"], 2, "Detected scanned tab count")
    assert_equal(
        detected["candidate_sources"],
        ["text:facebook_business_content_id:business_content_id"],
        "Detected candidate source summary",
    )

    missed_context = FakeContext(
        [
            FakePage("https://business.facebook.com/latest/composer"),
            FakePage("https://www.facebook.com/", error=RuntimeError("page closed")),
        ]
    )
    missed = detect_post_url_in_context(missed_context, "facebook")
    assert_equal(missed["detected"], False, "Missed post URL")
    assert_equal(missed["candidate_count"], 0, "Missed candidate count")
    assert_equal(missed["scanned_tab_count"], 2, "Missed scanned tab count")
    assert_equal(missed["scanner_error_count"], 1, "Missed scanner error count")
    assert_equal(missed["scanner_errors"][0]["source"], "error:RuntimeError", "Scanner error source")


def test_tiktok_conflicting_candidates_are_not_detected() -> None:
    from bitbrowser_rpa_example import detect_post_url_in_context

    context = FakeContext(
        [
            FakePage(
                "https://www.tiktok.com/tiktokstudio/content",
                [
                    {
                        "source": "text:tiktok_item_id",
                        "url": "https://www.tiktok.com/player/v1/7675641440810093844",
                        "text": "old item_id from Studio state",
                    },
                    {
                        "source": "text:tiktok_public_url",
                        "url": "https://www.tiktok.com/@xiojian9527/video/7677501759295687956",
                        "text": "new public video",
                    },
                ],
            )
        ]
    )
    result = detect_post_url_in_context(context, "tiktok")
    assert_equal(result["detected"], False, "TikTok conflicting IDs are not auto-detected")
    assert_equal(result["error_type"], "POST_URL_CONFLICT", "TikTok conflict error type")
    assert_equal(
        result["conflicting_post_ids"],
        ["7675641440810093844", "7677501759295687956"],
        "TikTok conflict lists both IDs",
    )


def test_tiktok_raw_item_id_is_diagnostic_only() -> None:
    from bitbrowser_rpa_example import detect_post_url_in_context

    context = FakeContext(
        [
            FakePage(
                "https://www.tiktok.com/tiktokstudio/content",
                [
                    {
                        "source": "text:tiktok_item_id",
                        "url": "https://www.tiktok.com/player/v1/7675641440810093844",
                        "text": "item_id only",
                    }
                ],
            )
        ]
    )
    result = detect_post_url_in_context(context, "tiktok")
    assert_equal(result["detected"], False, "TikTok raw item_id is not auto-detected")
    assert_equal(result["error_type"], "TIKTOK_POST_URL_NOT_PUBLIC", "TikTok raw item_id error type")


def test_tiktok_studio_query_public_fallback_is_not_auto_detected() -> None:
    from bitbrowser_rpa_example import detect_post_url_in_context

    context = FakeContext(
        [
            FakePage(
                "https://www.tiktok.com/tiktokstudio/content?item_id=7677501759295687956&username=xiojian9527",
                [],
            )
        ]
    )
    result = detect_post_url_in_context(context, "tiktok")
    assert_equal(result["detected"], False, "TikTok Studio query fallback is not auto-detected")
    assert_equal(result["error_type"], "TIKTOK_POST_URL_NOT_PUBLIC", "TikTok Studio query fallback error type")


def test_tiktok_same_id_public_url_can_be_detected() -> None:
    from bitbrowser_rpa_example import detect_post_url_in_context

    context = FakeContext(
        [
            FakePage(
                "https://www.tiktok.com/tiktokstudio/content",
                [
                    {
                        "source": "text:tiktok_item_id",
                        "url": "https://www.tiktok.com/player/v1/7677501759295687956",
                        "text": "same item_id from Studio state",
                    },
                    {
                        "source": "text:tiktok_public_url",
                        "url": "https://www.tiktok.com/@xiojian9527/video/7677501759295687956",
                        "text": "same public video",
                    },
                ],
            )
        ]
    )
    result = detect_post_url_in_context(context, "tiktok")
    assert_equal(result["detected"], True, "TikTok same ID public URL is detected")
    assert_equal(
        result["post_url"],
        "https://www.tiktok.com/@xiojian9527/video/7677501759295687956",
        "TikTok same ID prefers public URL",
    )
    assert_equal(result["auto_write_safe"], True, "TikTok public URL is auto-write safe")


def test_tiktok_studio_content_list_prefers_latest_row() -> None:
    from bitbrowser_rpa_example import detect_post_url_in_context

    context = FakeContext(
        [
            FakePage(
                "https://www.tiktok.com/tiktokstudio/content",
                [
                    {
                        "source": "text:tiktok_studio_content_public_url",
                        "url": "https://www.tiktok.com/@xiojian9527/video/7677501759295687956",
                        "text": "new row Public 24 Aug, 3:48 pm",
                        "studio_row_index": "0",
                        "studio_privacy": "Public",
                        "studio_created_text": "24 Aug, 3:48 pm",
                    },
                    {
                        "source": "text:tiktok_studio_content_public_url",
                        "url": "https://www.tiktok.com/@xiojian9527/video/7675641440810093844",
                        "text": "old row Private 19 Aug, 3:29 pm",
                        "studio_row_index": "1",
                        "studio_privacy": "Private",
                        "studio_created_text": "19 Aug, 3:29 pm",
                    },
                    {
                        "source": "text:tiktok_item_id",
                        "url": "https://www.tiktok.com/player/v1/7675641440810093844",
                        "text": "old item_id from page state",
                    },
                ],
            )
        ]
    )
    result = detect_post_url_in_context(context, "tiktok")
    assert_equal(result["detected"], True, "TikTok Studio content list is detected")
    assert_equal(
        result["post_url"],
        "https://www.tiktok.com/@xiojian9527/video/7677501759295687956",
        "TikTok Studio content list prefers latest row",
    )
    assert_equal(result["source"], "text:tiktok_studio_content_public_url", "TikTok Studio row source")


def test_tiktok_studio_latest_private_is_not_detected() -> None:
    from bitbrowser_rpa_example import detect_post_url_in_context

    context = FakeContext(
        [
            FakePage(
                "https://www.tiktok.com/tiktokstudio/content",
                [
                    {
                        "source": "text:tiktok_studio_content_public_url",
                        "url": "https://www.tiktok.com/@xiojian9527/video/7677501759295687956",
                        "text": "new row Private 24 Aug, 3:48 pm",
                        "studio_row_index": "0",
                        "studio_privacy": "Private",
                        "studio_created_text": "24 Aug, 3:48 pm",
                    }
                ],
            )
        ]
    )
    result = detect_post_url_in_context(context, "tiktok")
    assert_equal(result["detected"], False, "TikTok latest private row is not detected")
    assert_equal(result["error_type"], "TIKTOK_STUDIO_LATEST_NOT_PUBLIC", "TikTok latest private error type")


def test_facebook_calendar_candidate_order() -> None:
    checked_at = datetime(2026, 8, 19, 16, 13, 39)
    candidates = [
        {
            "post_url": "https://www.facebook.com/1237975296070200/posts/122106457737435838",
            "platform_post_id": "122106457737435838",
            "text": "11:40",
            "score": 150,
            "tab_index": 2,
        },
        {
            "post_url": "https://www.facebook.com/1237975296070200/posts/122106547767435838",
            "platform_post_id": "122106547767435838",
            "text": "15:45",
            "score": 150,
            "tab_index": 5,
        },
        {
            "post_url": "https://www.facebook.com/1237975296070200/posts/122106554229435838",
            "platform_post_id": "122106554229435838",
            "text": "16:08",
            "score": 150,
            "tab_index": 5,
        },
    ]
    ranked = sorted(candidates, key=lambda item: _post_candidate_sort_key(item, "facebook", checked_at))
    assert_equal(
        ranked[0]["platform_post_id"],
        "122106554229435838",
        "Prefer latest content-calendar post near checked time",
    )
    assert_equal(
        _facebook_candidate_time_delta_seconds("23:59", datetime(2026, 8, 20, 0, 3, 0)),
        240,
        "Facebook calendar time wraps across midnight",
    )


def main() -> int:
    tests = [
        test_tiktok_post_ids,
        test_facebook_post_ids,
        test_facebook_embedded_url_candidates,
        test_detection_diagnostics,
        test_tiktok_conflicting_candidates_are_not_detected,
        test_tiktok_raw_item_id_is_diagnostic_only,
        test_tiktok_studio_query_public_fallback_is_not_auto_detected,
        test_tiktok_same_id_public_url_can_be_detected,
        test_tiktok_studio_content_list_prefers_latest_row,
        test_tiktok_studio_latest_private_is_not_detected,
        test_facebook_calendar_candidate_order,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"URL detection self-test passed: {len(tests)} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
