from __future__ import annotations

import argparse
import json
from typing import Any

import win32com.client


def used_range_values(sheet: Any, max_rows: int, max_cols: int) -> list[list[Any]]:
    used = sheet.UsedRange
    rows = min(int(used.Rows.Count), max_rows)
    cols = min(int(used.Columns.Count), max_cols)
    if rows <= 0 or cols <= 0:
        return []
    values = sheet.Range(sheet.Cells(1, 1), sheet.Cells(rows, cols)).Value
    if values is None:
        return []
    if rows == 1:
        values = [values]
    return [list(row if isinstance(row, tuple) else (row,)) for row in values]


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect open Excel workbooks fed by R|Trader Pro live streaming.")
    parser.add_argument("--rows", type=int, default=12)
    parser.add_argument("--cols", type=int, default=20)
    args = parser.parse_args()

    excel = win32com.client.GetActiveObject("Excel.Application")
    result = []
    for workbook in excel.Workbooks:
        wb_info = {"name": workbook.Name, "path": workbook.FullName, "sheets": []}
        for sheet in workbook.Worksheets:
            values = used_range_values(sheet, args.rows, args.cols)
            wb_info["sheets"].append(
                {
                    "name": sheet.Name,
                    "rows": values,
                }
            )
        result.append(wb_info)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
