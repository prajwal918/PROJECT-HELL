from __future__ import annotations

import ctypes
import platform
from pathlib import Path
from typing import Any

from .base_gate import BaseGate


class GateZ7(BaseGate):
    gate_name = "gate_Z7"
    priority = 33

    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2] / "core"
        name = "lag_engine.dll" if platform.system() == "Windows" else "lag_engine.so"
        self.lib_path = root / name
        self.lib = None
        if self.lib_path.exists():
            self.lib = ctypes.CDLL(str(self.lib_path))
            self.lib.check_lag_arbitrage.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
            self.lib.check_lag_arbitrage.restype = ctypes.c_int

    def evaluate(self, tick: dict[str, Any]) -> bool:
        rithmic_price = float(tick.get("rithmic_price", tick.get("bid", 0.0)))
        deriv_price = float(tick.get("deriv_price", tick.get("ask", 0.0)))
        threshold = float(tick.get("lag_threshold_pips", 1.5))
        pip_size = float(tick.get("pip_size", 0.0001))
        if self.lib is not None:
            return bool(self.lib.check_lag_arbitrage(rithmic_price, deriv_price, threshold))
        if pip_size <= 0:
            return False
        lag_pips = abs(rithmic_price - deriv_price) / pip_size
        return lag_pips <= threshold
