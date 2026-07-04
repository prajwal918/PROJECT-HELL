from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ROOTS = [
    ROOT / "vendor" / "rithmic" / "rapi",
    Path(r"C:\Rithmic\RAPI"),
    Path(r"C:\Rithmic\RAPIPlus"),
    Path(r"C:\Program Files\Rithmic\RAPI"),
    Path(r"C:\Program Files (x86)\Rithmic\RAPI"),
    Path(r"C:\Program Files\NinjaTrader 8\bin"),
    Path(r"C:\Quantower\TradingPlatform\v1.145.17\bin\Vendors\RithmicVendor"),
]

HEADER_NAMES = {"RApi.h", "RApiPlus.h", "RApiLoginParams.h"}
LIB_NAMES = {"RApi.lib", "RApiPlus.lib", "rapiplus.lib"}
DLL_NAMES = {"RApi.dll", "RApiPlus.dll", "rapiplus.dll"}


def find_files(root: Path, names: set[str]) -> list[str]:
    if not root.exists():
        return []
    found = []
    lowered = {name.lower() for name in names}
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() in lowered:
            found.append(str(path))
    return found


def main() -> None:
    report = []
    all_headers: list[str] = []
    all_libs: list[str] = []
    all_dlls: list[str] = []

    for root in CANDIDATE_ROOTS:
        headers = find_files(root, HEADER_NAMES)
        libs = find_files(root, LIB_NAMES)
        dlls = find_files(root, DLL_NAMES)
        if headers or libs or dlls or root.exists():
            report.append(
                {
                    "root": str(root),
                    "exists": root.exists(),
                    "headers": headers,
                    "libs": libs,
                    "dlls": dlls,
                }
            )
        all_headers.extend(headers)
        all_libs.extend(libs)
        all_dlls.extend(dlls)

    ready = bool(all_headers and (all_libs or all_dlls))
    print(json.dumps({"ready": ready, "roots": report}, indent=2))
    if not ready:
        raise SystemExit(
            "RAPI+ SDK is not fully installed. Need RApi.h/RApiPlus.h plus lib/DLL files from the Rithmic R | API+ Dev Kit."
        )


if __name__ == "__main__":
    main()
