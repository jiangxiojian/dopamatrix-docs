"""Self-test the static customer report page generator."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rpa_customer_report_page import generate_report_page  # noqa: E402


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def run_report(detail_csv: Path, overview_csv: Path) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "customer_report.html"
        args = type(
            "Args",
            (),
            {
                "detail_csv": str(detail_csv),
                "overview_csv": str(overview_csv),
                "output_html": str(output),
                "client_id": "",
            },
        )()
        generated = generate_report_page(args)
        if not generated.is_file():
            raise AssertionError(f"report not created: {generated}")
        return generated.read_text(encoding="utf-8")


def test_batch_sample() -> None:
    html = run_report(
        SCRIPT_DIR.parent.parent.parent / "output" / "publish-rpa" / "batch-sample-test" / "customer_report_seed.csv",
        SCRIPT_DIR.parent.parent.parent / "output" / "publish-rpa" / "batch-sample-test" / "customer_report_overview.csv",
    )
    assert_contains(html, "客户与平台概览", "batch overview section")
    assert_contains(html, "RPA-BATCH-SAMPLE", "batch product key")
    assert_contains(html, "DMX", "batch client key")
    assert_contains(html, "待补指标", "batch pending metrics")


def test_published_single() -> None:
    html = run_report(
        SCRIPT_DIR.parent.parent.parent / "output" / "publish-rpa" / "batch-sample-test" / "fb-image-post-customer_report_seed.csv",
        SCRIPT_DIR.parent.parent.parent / "output" / "publish-rpa" / "batch-sample-test" / "fb-image-post-customer_report_overview.csv",
    )
    assert_contains(html, "已发布", "single published status")
    assert_contains(html, "100.00%", "single success rate")
    assert_contains(html, "122106554229435838", "single post id")


def main() -> int:
    test_batch_sample()
    print("PASS test_batch_sample")
    test_published_single()
    print("PASS test_published_single")
    print("Customer report page self-test passed: 2 groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
