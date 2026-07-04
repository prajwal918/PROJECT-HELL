from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseGate(ABC):
    gate_name = "gate_BASE"
    priority = 10_000

    @abstractmethod
    def evaluate(self, tick: dict[str, Any]) -> bool:
        """Return True when the tick passes this gate."""
