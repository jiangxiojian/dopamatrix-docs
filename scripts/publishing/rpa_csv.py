"""Read operator CSV files without losing values from malformed rows."""

from __future__ import annotations

import csv
from pathlib import Path


class CSVFormatError(ValueError):
    pass


def read_csv_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, strict=True)
        try:
            headers = next(reader, [])
            fieldnames = [field for field in headers if field.strip()]
            if len(set(fieldnames)) != len(fieldnames):
                raise CSVFormatError(f"CSV 表头有重复列名，请修正后重试。\n文件：{path}")
            rows = []
            for values in reader:
                if not values:
                    continue
                extra = values[len(headers):]
                if any(value.strip() for value in extra):
                    raise CSVFormatError(
                        f"CSV 第 {reader.line_num} 行列数不一致：表头 {len(headers)} 列，"
                        f"本行 {len(headers) + len(extra)} 列。\n文件：{path}\n"
                        '文案含英文逗号、双引号或换行时，请用表格软件编辑并另存为 CSV UTF-8；'
                        '手工编辑时需用英文双引号包住整个字段，字段内的双引号写成两个双引号。'
                    )
                pairs = list(zip(headers, values + [""] * max(0, len(headers) - len(values))))
                if any(value.strip() for key, value in pairs if not key.strip()):
                    raise CSVFormatError(
                        f"CSV 第 {reader.line_num} 行在无列名的列中有内容，请补齐表头。\n文件：{path}"
                    )
                rows.append({key: value for key, value in pairs if key.strip()})
            return fieldnames, rows
        except csv.Error as exc:
            raise CSVFormatError(
                f"CSV 第 {reader.line_num} 行附近格式错误，请检查字段引号。\n文件：{path}"
            ) from exc


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    _, rows = read_csv_table(path)
    return [{key: value.strip() for key, value in row.items()} for row in rows]
