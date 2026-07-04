from __future__ import annotations

import argparse
import json
import socket
import time
from typing import Any

import win32com.client
import pywintypes


FIELD_ALIASES = {
    "symbol": ("symbol", "contract", "instrument"),
    "bid": ("bid", "best bid", "bid price"),
    "bid_size": ("bid size", "bidsize", "bid qty", "bid quantity", "bid sz"),
    "ask": ("ask", "best ask", "ask price", "offer", "offer price"),
    "ask_size": ("ask size", "asksize", "ask qty", "ask quantity", "ask sz", "offer size"),
}


def normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def find_header(sheet: Any, max_scan_rows: int = 20, max_scan_cols: int = 60) -> tuple[int, dict[str, int]]:
    used = sheet.UsedRange
    rows = min(int(used.Rows.Count), max_scan_rows)
    cols = min(int(used.Columns.Count), max_scan_cols)

    best_row = 0
    best_mapping: dict[str, int] = {}
    for row in range(1, rows + 1):
        values = sheet.Range(sheet.Cells(row, 1), sheet.Cells(row, cols)).Value
        if values is None:
            continue
        if isinstance(values, tuple) and values and isinstance(values[0], tuple):
            row_values = list(values[0])
        else:
            row_values = list(values if isinstance(values, tuple) else (values,))
        mapping: dict[str, int] = {}
        lowered = [normalize(v) for v in row_values]
        for field, aliases in FIELD_ALIASES.items():
            for idx, name in enumerate(lowered, start=1):
                if name in aliases:
                    mapping[field] = idx
                    break
        if len(mapping) > len(best_mapping):
            best_row = row
            best_mapping = mapping

    required = {"symbol", "bid", "ask"}
    missing = required - set(best_mapping)
    if missing:
        raise RuntimeError(f"Could not find required columns {sorted(missing)} in sheet '{sheet.Name}'.")

    return best_row, best_mapping


def get_workbook(excel: Any, workbook_name: str | None) -> Any:
    if workbook_name:
        for workbook in excel.Workbooks:
            if workbook.Name.lower() == workbook_name.lower():
                return workbook
        raise RuntimeError(f"Workbook not found: {workbook_name}")
    if excel.Workbooks.Count == 0:
        raise RuntimeError("No open Excel workbook found. Create a live streaming spreadsheet from R|Trader Pro first.")
    return excel.Workbooks(1)


def get_sheet(workbook: Any, sheet_name: str | None) -> Any:
    if sheet_name:
        return workbook.Worksheets(sheet_name)
    for sheet in workbook.Worksheets:
        name = sheet.Name.lower()
        if "full" in name or "quote" in name or "market" in name:
            return sheet
    return workbook.Worksheets(1)


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def cell_value(sheet: Any, row: int, col: int, retries: int = 5) -> Any:
    for attempt in range(retries):
        try:
            return sheet.Cells(row, col).Value
        except pywintypes.com_error:
            if attempt == retries - 1:
                raise
            time.sleep(0.05)
    return None


def build_dom_json(bid: float, bid_size: float, ask: float, ask_size: float) -> str:
    return json.dumps(
        {
            "bids": [{"price": bid, "size": bid_size}],
            "asks": [{"price": ask, "size": ask_size}],
            "source": "rtrader_excel",
        },
        separators=(",", ":"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Forward R|Trader Pro Excel live stream rows to OVERSEER UDP.")
    parser.add_argument("--workbook")
    parser.add_argument("--sheet")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=65000)
    parser.add_argument("--interval", type=float, default=0.10)
    parser.add_argument("--max-row", type=int, default=200)
    args = parser.parse_args()

    excel = win32com.client.GetActiveObject("Excel.Application")
    workbook = get_workbook(excel, args.workbook)
    sheet = get_sheet(workbook, args.sheet)
    header_row, columns = find_header(sheet)
    print(f"Using workbook={workbook.Name!r} sheet={sheet.Name!r} header_row={header_row} columns={columns}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    last_payload_by_symbol: dict[str, str] = {}
    sent = 0

    while True:
        for row in range(header_row + 1, args.max_row + 1):
            try:
                symbol = str(cell_value(sheet, row, columns["symbol"]) or "").strip()
                if not symbol:
                    continue

                bid = to_float(cell_value(sheet, row, columns["bid"]))
                ask = to_float(cell_value(sheet, row, columns["ask"]))
                if bid <= 0 or ask <= 0 or ask <= bid:
                    continue

                bid_size = to_float(cell_value(sheet, row, columns.get("bid_size", columns["bid"])))
                ask_size = to_float(cell_value(sheet, row, columns.get("ask_size", columns["ask"])))
            except pywintypes.com_error as exc:
                print(f"Excel COM busy; retrying next cycle: {exc}")
                break
            delta = ask_size - bid_size
            timestamp_ms = int(time.time() * 1000)
            dom_json = build_dom_json(bid, bid_size, ask, ask_size)
            payload = "|".join(
                [
                    symbol,
                    f"{bid:.10f}",
                    f"{bid_size:.10f}",
                    f"{ask:.10f}",
                    f"{ask_size:.10f}",
                    dom_json,
                    f"{delta:.10f}",
                    str(timestamp_ms),
                ]
            )

            if last_payload_by_symbol.get(symbol) == payload:
                continue
            last_payload_by_symbol[symbol] = payload
            sock.sendto(payload.encode("utf-8"), (args.host, args.port))
            sent += 1
            if sent % 100 == 0:
                print(f"sent={sent} last={symbol} bid={bid} ask={ask}")

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
