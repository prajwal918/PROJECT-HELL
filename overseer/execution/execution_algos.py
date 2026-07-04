"""Institutional Execution Engine.

VWAP execution algorithm — slice parent order to track volume-weighted average price.
TWAP execution algorithm — time-weighted order slicing.
Iceberg execution — hide true order size from the market.
Implementation Shortfall — minimize total cost (market impact + timing risk).
Almgren-Chriss optimal execution trajectory — mathematically optimal slicing pace.
POV (Percentage of Volume) — participate at a fixed % of market volume.

These are how institutions actually ENTER trades. A single market order
on CME futures at 1+ lot size creates visible market impact. Institutions
slice orders to minimize footprint.
"""
from __future__ import annotations

import logging
import math
import os
import time
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.execution_algo")

VWAP_PARTICIPATION_RATE = float(os.getenv("VWAP_PARTICIPATION_RATE", "0.10"))
TWAP_SLICE_INTERVAL_MS = float(os.getenv("TWAP_SLICE_INTERVAL_MS", "5000"))
ICEBERG_DISPLAY_SIZE = float(os.getenv("ICEBERG_DISPLAY_SIZE", "1.0"))
IS_ALPHA_RISK = float(os.getenv("IS_ALPHA_RISK", "0.5"))
IS_SIGMA_IMPACT = float(os.getenv("IS_SIGMA_IMPACT", "0.5"))
ALMGREN_SIGMA = float(os.getenv("ALMGREN_SIGMA", "0.001"))
ALMGREN_LIQUIDITY = float(os.getenv("ALMGREN_LIQUIDITY", "0.1"))
ALMGREN_GAMMA = float(os.getenv("ALMGREN_GAMMA", "0.3"))
ALMGREN_ETA = float(os.getenv("ALMGREN_ETA", "0.1"))
POV_TARGET_RATE = float(os.getenv("POV_TARGET_RATE", "0.05"))
POV_MAX_RATE = float(os.getenv("POV_MAX_RATE", "0.15"))
MIN_CHILD_SIZE = float(os.getenv("MIN_CHILD_SIZE", "0.01"))


class ParentOrder:
    __slots__ = ("order_id", "symbol", "direction", "total_size", "filled_size", "avg_fill_price", "start_time", "algo", "status", "children")

    def __init__(self, order_id: str, symbol: str, direction: str, total_size: float, algo: str = "vwap") -> None:
        self.order_id = order_id
        self.symbol = symbol
        self.direction = direction
        self.total_size = total_size
        self.filled_size: float = 0.0
        self.avg_fill_price: float = 0.0
        self.start_time: float = time.time()
        self.algo = algo
        self.status: str = "pending"
        self.children: list[dict[str, Any]] = []


class VWAPAlgo:
    """VWAP execution — volume-weighted time slicing.

    Distributes order quantity according to historical volume profile
    across time buckets. Participates at VWAP_PARTICIPATION_RATE of market volume.
    """

    def __init__(self) -> None:
        self._volume_profile: dict[str, deque[float]] = {}
        self._time_buckets: int = 12

    def update_volume(self, symbol: str, volume: float, timestamp: float) -> None:
        if symbol not in self._volume_profile:
            self._volume_profile[symbol] = deque(maxlen=500)
        self._volume_profile[symbol].append(volume)

    def compute_slices(self, parent: ParentOrder, n_slices: int = 10) -> list[dict[str, Any]]:
        remaining = parent.total_size - parent.filled_size
        if remaining <= 0:
            return []
        volumes = list(self._volume_profile.get(parent.symbol, []))
        if len(volumes) < 20:
            per_slice = remaining / n_slices
            return [
                {"size": per_slice, "delay_ms": i * TWAP_SLICE_INTERVAL_MS / n_slices}
                for i in range(n_slices)
            ]
        vol_arr = np.array(volumes[-120:])
        bucket_size = max(1, len(vol_arr) // self._time_buckets)
        bucket_vols = []
        for i in range(self._time_buckets):
            start = i * bucket_size
            end = min(start + bucket_size, len(vol_arr))
            bucket_vols.append(float(vol_arr[start:end].sum()) if start < len(vol_arr) else 1.0)
        total_vol = sum(bucket_vols)
        if total_vol <= 0:
            per_slice = remaining / n_slices
            return [{"size": per_slice, "delay_ms": i * TWAP_SLICE_INTERVAL_MS} for i in range(n_slices)]
        weights = [v / total_vol for v in bucket_vols]
        slices = []
        cumulative = 0.0
        for i, w in enumerate(weights):
            size = remaining * w
            if size < MIN_CHILD_SIZE and i < len(weights) - 1:
                cumulative += size
                continue
            size += cumulative
            cumulative = 0.0
            slices.append({
                "size": round(size, 2),
                "delay_ms": (i + 1) * TWAP_SLICE_INTERVAL_MS / self._time_buckets,
                "participation_rate": VWAP_PARTICIPATION_RATE,
            })
        if cumulative > MIN_CHILD_SIZE:
            if slices:
                slices[-1]["size"] = round(slices[-1]["size"] + cumulative, 2)
            else:
                slices.append({"size": round(cumulative, 2), "delay_ms": 0, "participation_rate": VWAP_PARTICIPATION_RATE})
        return slices


class TWAPAlgo:
    """TWAP execution — uniform time slicing."""

    def compute_slices(self, parent: ParentOrder, duration_ms: float = 60000) -> list[dict[str, Any]]:
        remaining = parent.total_size - parent.filled_size
        if remaining <= 0:
            return []
        n_slices = max(1, int(duration_ms / TWAP_SLICE_INTERVAL_MS))
        per_slice = remaining / n_slices
        return [
            {"size": round(per_slice, 2), "delay_ms": (i + 1) * TWAP_SLICE_INTERVAL_MS}
            for i in range(n_slices)
        ]


class IcebergAlgo:
    """Iceberg execution — display only a small portion of the true order size.

    Sends child orders of ICEBERG_DISPLAY_SIZE. When one fills, immediately
    sends the next. Market only sees the tip of the iceberg.
    """

    def compute_slices(self, parent: ParentOrder) -> list[dict[str, Any]]:
        remaining = parent.total_size - parent.filled_size
        if remaining <= 0:
            return []
        slices = []
        size_left = remaining
        while size_left > 0:
            child_size = min(ICEBERG_DISPLAY_SIZE, size_left)
            slices.append({"size": round(child_size, 2), "delay_ms": 0, "iceberg": True})
            size_left -= child_size
        return slices


class ImplementationShortfall:
    """Implementation Shortfall algorithm.

    Minimizes total cost = market impact + timing risk.
    Trades off: trading too fast (high impact) vs too slow (price drift).
    front-loads when alpha is high, back-loads when impact is the concern.
    """

    def compute_trajectory(self, parent: ParentOrder, urgency: float = 0.5) -> list[dict[str, Any]]:
        remaining = parent.total_size - parent.filled_size
        if remaining <= 0:
            return []
        n = 10
        kappa = math.sqrt(IS_ALPHA_RISK / (2 * IS_SIGMA_IMPACT))
        x_total = remaining
        slices = []
        prev_x = 0.0
        for i in range(1, n + 1):
            t = i / n
            if urgency > 0.5:
                fraction = (1 - math.exp(-kappa * t * 2)) / (1 - math.exp(-kappa * 2))
            else:
                fraction = t ** (1 + urgency)
            x_t = x_total * fraction
            child_size = x_t - prev_x
            prev_x = x_t
            if child_size >= MIN_CHILD_SIZE:
                slices.append({
                    "size": round(child_size, 2),
                    "delay_ms": i * TWAP_SLICE_INTERVAL_MS / n,
                    "urgency": urgency,
                })
        return slices


class AlmgrenChriss:
    """Almgren-Chriss optimal execution trajectory.

    Minimizes E[cost] + lambda * Var[cost] where:
    - E[cost] = temporary impact + permanent impact
    - Var[cost] = timing risk from price volatility
    - lambda = risk aversion parameter

    Produces the mathematically optimal trading schedule.
    """

    def __init__(self) -> None:
        self.sigma = ALMGREN_SIGMA
        self.liquidity = ALMGREN_LIQUIDITY
        self.gamma = ALMGREN_GAMMA
        self.eta = ALMGREN_ETA
        self._risk_aversion: float = 0.5
        self._estimated_lambda: float = 0.0

    def update_calibration(self, kyle_lambda: float = 0.0, vol: float = 0.0) -> None:
        if vol > 0:
            self.sigma = vol
        if kyle_lambda > 0:
            self.liquidity = 1.0 / kyle_lambda

    def compute_trajectory(self, parent: ParentOrder, risk_aversion: float = 0.5, duration_ms: float = 60000) -> list[dict[str, Any]]:
        remaining = parent.total_size - parent.filled_size
        if remaining <= 0:
            return []
        self._risk_aversion = risk_aversion
        X = remaining
        T = 10.0
        n = 10
        kappa = math.sqrt(self.gamma * risk_aversion / self.eta) if self.eta > 1e-10 else 1.0
        sinh_kT = math.sinh(kappa * T)
        if abs(sinh_kT) < 1e-10:
            sinh_kT = 1e-10
        slices = []
        prev_x = X
        for i in range(1, n + 1):
            t = i * T / n
            x_t = X * (sinh_kT - math.sinh(kappa * (T - t))) / sinh_kT if kappa > 1e-6 else X * t / T
            child_size = prev_x - x_t
            prev_x = x_t
            if child_size >= MIN_CHILD_SIZE:
                slices.append({
                    "size": round(child_size, 2),
                    "delay_ms": i * duration_ms / n,
                    "kappa": round(kappa, 6),
                    "remaining_after": round(x_t, 2),
                })
        if prev_x >= MIN_CHILD_SIZE:
            if slices:
                slices[-1]["size"] = round(slices[-1]["size"] + prev_x, 2)
            else:
                slices.append({"size": round(prev_x, 2), "delay_ms": duration_ms, "kappa": round(kappa, 6), "remaining_after": 0.0})
        return slices

    def estimate_market_impact(self, order_size: float, duration_ticks: int = 10) -> dict[str, float]:
        if order_size <= 0:
            return {"temporary_impact": 0, "permanent_impact": 0, "total_impact_bps": 0}
        temp_impact = self.eta * (order_size / max(1, duration_ticks))
        perm_impact = self.gamma * order_size
        total = temp_impact + perm_impact
        return {
            "temporary_impact": round(temp_impact, 6),
            "permanent_impact": round(perm_impact, 6),
            "total_impact_bps": round(total * 10000, 2),
            "optimal_duration_ticks": max(1, int(math.sqrt(self.eta * order_size / (0.5 * self.sigma ** 2 * self._risk_aversion))) if self.sigma > 0 else 1),
        }


class POVAlgo:
    """Percentage of Volume algorithm — participate at fixed % of market volume."""

    def __init__(self) -> None:
        self._recent_volume: dict[str, deque[tuple[float, float]]] = {}

    def update_market_volume(self, symbol: str, volume: float, timestamp: float) -> None:
        if symbol not in self._recent_volume:
            self._recent_volume[symbol] = deque(maxlen=1000)
        self._recent_volume[symbol].append((timestamp, volume))

    def compute_next_slice(self, parent: ParentOrder, market_volume_rate: float = 0.0) -> dict[str, Any]:
        remaining = parent.total_size - parent.filled_size
        if remaining <= 0:
            return {"size": 0, "participation_rate": 0}
        if market_volume_rate <= 0:
            vols = list(self._recent_volume.get(parent.symbol, []))
            if len(vols) >= 10:
                recent_vols = [v for _, v in vols[-10:]]
                market_volume_rate = float(np.mean(recent_vols))
            else:
                market_volume_rate = remaining
        target_rate = min(POV_TARGET_RATE, POV_MAX_RATE)
        slice_size = market_volume_rate * target_rate
        slice_size = min(slice_size, remaining)
        slice_size = max(MIN_CHILD_SIZE, slice_size)
        return {
            "size": round(slice_size, 2),
            "participation_rate": round(target_rate, 4),
            "market_volume_rate": round(market_volume_rate, 2),
        }


class ExecutionAlgoEngine:
    """Unified execution algorithm engine — select algo based on conditions."""

    def __init__(self) -> None:
        self.vwap = VWAPAlgo()
        self.twap = TWAPAlgo()
        self.iceberg = IcebergAlgo()
        self.is_algo = ImplementationShortfall()
        self.almgren = AlmgrenChriss()
        self.pov = POVAlgo()
        self._active_orders: dict[str, ParentOrder] = {}
        self._order_counter: int = 0

    def create_order(self, symbol: str, direction: str, total_size: float, algo: str = "auto") -> ParentOrder:
        self._order_counter += 1
        order_id = f"PA-{self._order_counter:06d}"
        if algo == "auto":
            algo = self._select_algo(symbol, total_size)
        parent = ParentOrder(order_id, symbol, direction, total_size, algo)
        self._active_orders[order_id] = parent
        return parent

    def _select_algo(self, symbol: str, size: float) -> str:
        if size <= ICEBERG_DISPLAY_SIZE:
            return "market"
        elif size <= ICEBERG_DISPLAY_SIZE * 3:
            return "iceberg"
        elif size <= ICEBERG_DISPLAY_SIZE * 10:
            return "vwap"
        else:
            return "almgren"

    def get_slices(self, parent: ParentOrder, **kwargs: Any) -> list[dict[str, Any]]:
        if parent.algo == "vwap":
            return self.vwap.compute_slices(parent, kwargs.get("n_slices", 10))
        elif parent.algo == "twap":
            return self.twap.compute_slices(parent, kwargs.get("duration_ms", 60000))
        elif parent.algo == "iceberg":
            return self.iceberg.compute_slices(parent)
        elif parent.algo == "is":
            return self.is_algo.compute_trajectory(parent, kwargs.get("urgency", 0.5))
        elif parent.algo == "almgren":
            return self.almgren.compute_trajectory(parent, kwargs.get("risk_aversion", 0.5), kwargs.get("duration_ms", 60000))
        elif parent.algo == "pov":
            next_slice = self.pov.compute_next_slice(parent, kwargs.get("market_volume_rate", 0))
            return [next_slice]
        else:
            return [{"size": parent.total_size, "delay_ms": 0}]

    def estimate_impact(self, symbol: str, size: float) -> dict[str, float]:
        return self.almgren.estimate_market_impact(size)

    def get_active_orders(self) -> dict[str, ParentOrder]:
        return dict(self._active_orders)

    def get_status(self) -> dict[str, Any]:
        return {
            "active_orders": len(self._active_orders),
            "total_created": self._order_counter,
        }
