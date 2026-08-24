"""Self-test the BitBrowser window -> account ledger sync helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bitbrowser_rpa_example import (  # noqa: E402
    ACCOUNT_LEDGER_FIELDS,
    BitBrowserClient,
    extract_bitbrowser_profile_rows,
    merge_account_ledger_rows,
    normalize_account_ledger_row,
)


def assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


class _FakeResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._body


def test_extract_nested_profile_rows() -> None:
    payload = {
        "success": True,
        "data": {
            "records": [
                {"id": "profile-1", "name": "TK-001", "platform": "tiktok"},
                {"browser_profile_id": "profile-2", "profileName": "FB-001", "platform": "facebook"},
            ],
            "items": [
                {"id": "profile-1", "name": "TK-001", "platform": "tiktok"},
            ],
        },
    }
    rows = extract_bitbrowser_profile_rows(payload)
    assert_equal(len(rows), 2, "nested BitBrowser rows")
    assert_equal(rows[0]["id"], "profile-1", "first row id")
    assert_equal(rows[1]["browser_profile_id"], "profile-2", "second row profile id")


def test_normalize_account_ledger_row() -> None:
    row = normalize_account_ledger_row(
        {
            "account_code": "acc-fb-001",
            "platform": "FB",
            "browser_id": "profile-9",
            "profileName": "fb-sg-main",
            "auto_content_check": "pause",
            "default": "yes",
            "notes": "main page",
            "ownerType": "client",
            "ownerClientId": "CUST-001",
            "authorizationType": "business_role",
            "region": "SG",
            "proxyRegion": "SG",
            "proxyProvider": "bitbrowser",
            "dailyPublishLimit": "3",
            "healthStatus": "WATCH",
            "healthNote": "needs review",
            "lastCheckedAt": "2026-08-24T10:00:00",
        }
    )
    assert_equal(row["account_key"], "acc-fb-001", "normalized account key")
    assert_equal(row["platform"], "facebook", "normalized platform")
    assert_equal(row["profile_id"], "profile-9", "normalized profile id")
    assert_equal(row["profile_name"], "fb-sg-main", "normalized profile name")
    assert_equal(row["default"], "Y", "normalized default flag")
    assert_equal(row["owner_client_id"], "CUST-001", "normalized client id")
    assert_equal(row["health_status"], "WATCH", "normalized health status")
    assert_equal(set(row.keys()), set(ACCOUNT_LEDGER_FIELDS), "normalized ledger fields")


def test_normalize_account_ledger_row_infers_missing_identity() -> None:
    row = normalize_account_ledger_row(
        {
            "profile_id": "profile-12",
            "profileName": "TK-PH-001",
        }
    )
    assert_equal(row["account_key"], "TK-PH-001", "inferred account key from profile name")
    assert_equal(row["platform"], "tiktok", "inferred platform from name hint")


def test_merge_account_ledger_rows() -> None:
    existing_rows = [
        {
            "account_key": "acc-fb-001",
            "platform": "facebook",
            "profile_id": "profile-1",
            "profile_name": "keep-name",
            "notes": "keep note",
            "health_status": "",
        }
    ]
    discovered_rows = [
        {
            "account_key": "acc-fb-001",
            "platform": "FB",
            "profile_id": "profile-1",
            "profile_name": "new-name",
            "notes": "new note",
            "health_status": "OK",
        },
        {
            "account_key": "acc-tk-001",
            "platform": "tiktok",
            "profile_id": "profile-2",
            "profile_name": "tk-main",
            "default": "true",
        },
    ]
    merged = merge_account_ledger_rows(existing_rows, discovered_rows)
    assert_equal(len(merged), 2, "merged row count")
    assert_equal(merged[0]["profile_name"], "keep-name", "existing row preserved")
    assert_equal(merged[0]["health_status"], "OK", "missing field filled")
    assert_equal(merged[0]["notes"], "keep note", "existing note preserved")
    assert_equal(merged[1]["account_key"], "acc-tk-001", "new row appended")
    assert_equal(merged[1]["default"], "Y", "new row normalized")


def test_bitbrowser_list_profiles() -> None:
    calls: list[dict[str, object]] = []

    def fake_post(url: str, json: dict[str, object], timeout: int):
        calls.append({"url": url, "json": dict(json), "timeout": timeout})
        return _FakeResponse(
            {
                "success": True,
                "data": {
                    "records": [
                        {"id": "profile-1", "name": "TK-001", "platform": "tiktok"},
                        {"browser_profile_id": "profile-2", "profileName": "FB-001", "platform": "facebook"},
                    ],
                    "total": 2,
                },
            }
        )

    with patch("bitbrowser_rpa_example.requests.post", fake_post):
        client = BitBrowserClient("http://127.0.0.1:54345", timeout=5)
        rows = client.list_profiles(page_size=50)

    assert_equal(len(calls), 1, "list_profiles call count")
    assert_equal(calls[0]["url"], "http://127.0.0.1:54345/browser/list", "list_profiles URL")
    assert_equal(calls[0]["json"]["pageSize"], 50, "list_profiles page size")
    assert_equal(len(rows), 2, "list_profiles result count")
    assert_equal(rows[0]["id"], "profile-1", "first returned profile")
    assert_equal(rows[1]["profileName"], "FB-001", "second returned profile")


def main() -> int:
    tests = [
        test_extract_nested_profile_rows,
        test_normalize_account_ledger_row,
        test_normalize_account_ledger_row_infers_missing_identity,
        test_merge_account_ledger_rows,
        test_bitbrowser_list_profiles,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"BitBrowser ledger sync self-test passed: {len(tests)} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
