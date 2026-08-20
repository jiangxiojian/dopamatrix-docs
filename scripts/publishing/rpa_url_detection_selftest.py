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
    def __init__(self, url: str, items: list[dict[str, str]]) -> None:
        self.url = url
        self._items = items

    def evaluate(self, script: str) -> list[dict[str, str]]:
        return self._items


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
        test_facebook_calendar_candidate_order,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"URL detection self-test passed: {len(tests)} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
