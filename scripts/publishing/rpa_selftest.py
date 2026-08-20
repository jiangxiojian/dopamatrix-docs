"""Run local self-tests for the DopaMatrix RPA publishing helpers."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import rpa_customer_report_page_selftest  # noqa: E402
import rpa_operator_console_selftest  # noqa: E402
import rpa_stability_selftest  # noqa: E402
import rpa_url_detection_selftest  # noqa: E402


def main() -> int:
    print("Running URL detection self-test...")
    rpa_url_detection_selftest.main()
    print()
    print("Running customer report page self-test...")
    rpa_customer_report_page_selftest.main()
    print()
    print("Running operator console self-test...")
    rpa_operator_console_selftest.main()
    print()
    print("Running popup and error stability self-test...")
    rpa_stability_selftest.main()
    print()
    print("RPA local self-tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
