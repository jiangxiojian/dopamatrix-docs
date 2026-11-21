"""Run local self-tests for the DopaMatrix RPA publishing helpers."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import rpa_customer_report_page_selftest  # noqa: E402
import rpa_csv_selftest  # noqa: E402
import rpa_entry_check_selftest  # noqa: E402
import rpa_publish_options_selftest  # noqa: E402
import rpa_ledger_sync_selftest  # noqa: E402
import rpa_operator_console_selftest  # noqa: E402
import rpa_stability_selftest  # noqa: E402
import rpa_url_detection_selftest  # noqa: E402
import rpa_tiktok_upload_selftest  # noqa: E402


def main() -> int:
    print("Running TikTok upload entry self-test...")
    rpa_tiktok_upload_selftest.main()
    print()
    print("Running CSV regression self-test...")
    rpa_csv_selftest.main()
    print()
    print("Running URL detection self-test...")
    rpa_url_detection_selftest.main()
    print()
    print("Running customer report page self-test...")
    rpa_customer_report_page_selftest.main()
    print()
    print("Running BitBrowser ledger sync self-test...")
    rpa_ledger_sync_selftest.main()
    print()
    print("Running operator console self-test...")
    rpa_operator_console_selftest.main()
    print()
    print("Running popup and error stability self-test...")
    rpa_stability_selftest.main()
    print()
    print("Running entry inspection self-test...")
    rpa_entry_check_selftest.main()
    print()
    print("Running publishing settings self-test...")
    rpa_publish_options_selftest.main()
    print()
    print("RPA local self-tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
