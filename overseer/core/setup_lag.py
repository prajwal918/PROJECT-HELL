from __future__ import annotations

import ctypes
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger("overseer.setup_lag")

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "lag_engine.c"
OUTPUT = ROOT / ("lag_engine.dll" if platform.system() == "Windows" else "lag_engine.so")


def compile_lag_engine() -> Path | None:
    gcc = shutil.which("gcc")
    command = ["gcc", "-O2", "-shared", "-fPIC", "-o", str(OUTPUT), str(SOURCE), "-lm"]
    LOGGER.info("Compile command: %s", " ".join(command))

    if gcc is None:
        LOGGER.warning("gcc is not available on PATH. Docker build will compile lag_engine.so.")
        return None

    subprocess.run(command, cwd=ROOT, check=True)
    LOGGER.info("Compiled %s", OUTPUT)
    return OUTPUT


def load_lag_engine() -> ctypes.CDLL | None:
    if not OUTPUT.exists():
        compiled = compile_lag_engine()
        if compiled is None:
            return None

    lib = ctypes.CDLL(str(OUTPUT))
    lib.check_lag_arbitrage.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
    lib.check_lag_arbitrage.restype = ctypes.c_int
    lib.calculate_cumulative_delta.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int,
    ]
    lib.calculate_cumulative_delta.restype = ctypes.c_double
    lib.atr_adaptive_threshold.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_double]
    lib.atr_adaptive_threshold.restype = ctypes.c_double
    return lib


if __name__ == "__main__":
    engine = load_lag_engine()
    if engine is None:
        LOGGER.info("Lag engine compile skipped on this host; source is ready for Docker/Linux compilation.")
    else:
        LOGGER.info("Lag engine loaded successfully.")
