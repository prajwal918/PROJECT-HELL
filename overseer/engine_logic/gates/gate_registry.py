from __future__ import annotations

import importlib
import inspect
import pkgutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .base_gate import BaseGate


class GateRegistry:
    def __init__(self) -> None:
        self.gates = self._load_gates()
        self._executor = ThreadPoolExecutor(max_workers=8)

    def _load_gates(self) -> list[BaseGate]:
        package = __package__ or "engine_logic.gates"
        gate_dir = Path(__file__).resolve().parent
        loaded: list[BaseGate] = []

        for module_info in pkgutil.iter_modules([str(gate_dir)]):
            if not module_info.name.startswith("gate_") or module_info.name == "gate_registry":
                continue
            module = importlib.import_module(f"{package}.{module_info.name}")
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if obj is BaseGate or not issubclass(obj, BaseGate):
                    continue
                if obj.__module__ != module.__name__:
                    continue
                loaded.append(obj())

        return sorted(loaded, key=lambda gate: (gate.priority, gate.gate_name))

    def evaluate(self, tick: dict[str, Any]) -> dict[str, bool]:
        def _eval_one(gate: BaseGate):
            try:
                return gate.gate_name, bool(gate.evaluate(tick))
            except Exception:
                return gate.gate_name, False

        results: dict[str, bool] = {}
        # Parallel evaluation using thread pool to maximize resource usage
        for name, res in self._executor.map(_eval_one, self.gates):
            results[name] = res
        return results


def evaluate(tick: dict[str, Any]) -> dict[str, bool]:
    return GateRegistry().evaluate(tick)
