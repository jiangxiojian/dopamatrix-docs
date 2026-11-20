"""Regression checks for CSV column errors and self-contained publish plans."""

from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from bitbrowser_rpa_example import (
    DEFAULT_DELIVERY_CSV_FILENAME,
    BitBrowserError,
    DeliveryRecord,
    _read_csv_rows,
    main as publisher_main,
    parse_args,
    run_single,
    record_for_media,
    update_publish_plan_row,
)
from dopa_matrix_publisher import fill_missing_plan_metadata
from rpa_csv import CSVFormatError, read_csv_rows, read_csv_table
from rpa_customer_report_page import read_csv_rows as read_report_page
from rpa_operator_console import read_csv_rows as read_console
from rpa_report_export import read_csv_rows as read_report
from rpa_workbench_server import read_account_health


READERS = (read_csv_rows, _read_csv_rows, read_console, read_report, read_report_page, read_account_health)


def test_csv_readers() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sample.csv"
        path.write_text('publish_id,caption,hashtags\nT1,"Pink, green, or yellow?\nSay ""hello"".",#BodyCare\nT2,Short caption\n', encoding="utf-8-sig")
        for reader in READERS:
            rows = reader(path)
            assert rows[0]["caption"].replace("\r\n", "\n") == 'Pink, green, or yellow?\nSay "hello".'
            assert rows[0]["hashtags"] == "#BodyCare"
            assert rows[1]["hashtags"] == ""
        path.write_text('publish_id,caption\nT1,Caption,, \n', encoding="utf-8-sig")
        for reader in READERS:
            assert reader(path) == [{"publish_id": "T1", "caption": "Caption"}]


def test_csv_errors_are_actionable() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sample.csv"
        path.write_text('publish_id,caption,hashtags\nT1,Caption,#Tag\nT2,Pink, green, or yellow?,#Tag\n', encoding="utf-8-sig")
        original = path.read_bytes()
        for reader in READERS:
            try:
                reader(path)
            except CSVFormatError as exc:
                assert "第 3 行" in str(exc)
                assert "表头 3 列，本行 5 列" in str(exc)
                assert str(path) in str(exc)
            else:
                raise AssertionError(f"{reader.__module__} accepted misaligned columns")
        for writer in (
            lambda: update_publish_plan_row(path, "T1", {"status": "READY"}),
            lambda: fill_missing_plan_metadata(path, client_id="C1"),
        ):
            try:
                writer()
            except CSVFormatError:
                pass
            else:
                raise AssertionError("writer accepted invalid CSV")
            assert path.read_bytes() == original


def test_headers_and_broken_quotes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sample.csv"
        path.write_text('publish_id,caption,\nT1,Caption,\n', encoding="utf-8-sig")
        assert read_csv_table(path) == (["publish_id", "caption"], [{"publish_id": "T1", "caption": "Caption"}])
        for text, message in (
            ('publish_id,caption,\nT1,Caption,orphaned value\n', "无列名"),
            ('publish_id,,,caption\nT1,orphaned value,,Caption\n', "无列名"),
            ('publish_id,caption,caption\nT1,First,Second\n', "重复列名"),
            ('publish_id,caption\nT1,"Unfinished\n', "字段引号"),
        ):
            path.write_text(text, encoding="utf-8-sig")
            try:
                read_csv_rows(path)
            except CSVFormatError as exc:
                assert message in str(exc)
                assert str(path) in str(exc)
            else:
                raise AssertionError("invalid header or quotation was accepted")


def test_plan_caption_does_not_reload_source() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        media = root / "video.mp4"
        media.write_bytes(b"preview-only")
        source = root / DEFAULT_DELIVERY_CSV_FILENAME
        source.write_text('video_filename,caption\nvideo.mp4,Pink, green, or yellow?\n', encoding="utf-8-sig")
        argv = ["--platform", "tiktok", "--profile-id", "test-profile", "--media", str(media),
                "--caption", "Caption already stored in plan", "--print-plan"]
        args = parse_args(argv)
        args.from_plan = True
        with patch("bitbrowser_rpa_example.BitBrowserClient", side_effect=AssertionError("preview must not connect to a browser")), redirect_stdout(io.StringIO()):
            payload = run_single(args)
        assert payload["plan"]["caption"] == "Caption already stored in plan"
        assert payload["plan"]["caption_source"] == "plan_csv"
        assert payload["plan"]["delivery_csv"] == ""
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            result = publisher_main(argv)
        assert result == 1
        assert "第 2 行" in stderr.getvalue()
        assert "AttributeError" not in stderr.getvalue()


def test_filename_matching_never_reuses_first_row() -> None:
    first = DeliveryRecord(video_filename="first.mp4", emotional_description="First caption", hashtags="#First")
    second = DeliveryRecord(video_filename="second.mp4", emotional_description="Second caption", hashtags="#Second")
    assert record_for_media([first, second], Path("second.mp4")) is second
    for records, media, expected in (
        ([first], "second.mp4", "没有"),
        ([first, second, second], "second.mp4", "重复"),
    ):
        try:
            record_for_media(records, Path(media))
        except BitBrowserError as exc:
            assert expected in str(exc)
            assert media in str(exc)
        else:
            raise AssertionError("missing/duplicate filename silently chose a caption")


def main() -> int:
    tests = [test_csv_readers, test_csv_errors_are_actionable, test_headers_and_broken_quotes,
             test_plan_caption_does_not_reload_source, test_filename_matching_never_reuses_first_row]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"CSV regression self-test passed: {len(tests)} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
