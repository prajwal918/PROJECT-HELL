from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class InstrumentProfile:
    symbol: str
    tick_size: float
    pip_size: float
    velocity_threshold: float
    spread_max_pips: float
    spread_bps_max: float
    atr_bps_min: float
    atr_bps_max: float
    lag_threshold_pips: float
    volume_baseline: float
    imbalance_threshold: float
    obi_threshold: float
    depth_min_contracts: float
    rr_min: float
    cross_spread_max_pips: float
    lead_lag_max_pips: float
    arb_min_lag_pips: float
    arb_max_lag_pips: float
    sl_pips: float
    tp_pips: float
    session_allow_asia: bool


_CME_DEFAULTS: dict[str, dict[str, Any]] = {
    "6E": {
        "tick_size": 0.0001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 2.0,
        "spread_bps_max": 5.0,
        "atr_bps_min": 0.5,
        "atr_bps_max": 30.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 5000.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 50.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 1.5,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 5.0,
        "tp_pips": 12.5,
        "session_allow_asia": False,
    },
    "6B": {
        "tick_size": 0.0001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0004,
        "spread_max_pips": 2.5,
        "spread_bps_max": 5.5,
        "atr_bps_min": 0.6,
        "atr_bps_max": 35.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 4000.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 40.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 1.5,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 7.0,
        "tp_pips": 17.5,
        "session_allow_asia": False,
    },
    "6J": {
        "tick_size": 0.01,
        "pip_size": 0.01,
        "velocity_threshold": 0.05,
        "spread_max_pips": 2.5,
        "spread_bps_max": 5.0,
        "atr_bps_min": 0.5,
        "atr_bps_max": 30.0,
        "lag_threshold_pips": 3.0,
        "volume_baseline": 3000.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 30.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 2.0,
        "lead_lag_max_pips": 5.0,
        "arb_min_lag_pips": 3.0,
        "arb_max_lag_pips": 15.0,
        "sl_pips": 8.0,
        "tp_pips": 20.0,
        "session_allow_asia": True,
    },
    "6A": {
        "tick_size": 0.0001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 2.5,
        "spread_bps_max": 5.0,
        "atr_bps_min": 0.5,
        "atr_bps_max": 28.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 2500.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 30.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 1.5,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 6.0,
        "tp_pips": 15.0,
        "session_allow_asia": True,
    },
    "6C": {
        "tick_size": 0.0001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 3.0,
        "spread_bps_max": 5.5,
        "atr_bps_min": 0.5,
        "atr_bps_max": 28.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 2000.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 30.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 2.0,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 6.0,
        "tp_pips": 15.0,
        "session_allow_asia": False,
    },
    "6N": {
        "tick_size": 0.0001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 3.0,
        "spread_bps_max": 5.5,
        "atr_bps_min": 0.4,
        "atr_bps_max": 25.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 1500.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 25.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 2.0,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 6.0,
        "tp_pips": 15.0,
        "session_allow_asia": True,
    },
    "6S": {
        "tick_size": 0.0001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 3.0,
        "spread_bps_max": 5.5,
        "atr_bps_min": 0.5,
        "atr_bps_max": 28.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 2000.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 30.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 2.0,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 6.0,
        "tp_pips": 15.0,
        "session_allow_asia": False,
    },
    "GC": {
        "tick_size": 0.1,
        "pip_size": 0.1,
        "velocity_threshold": 0.5,
        "spread_max_pips": 5.0,
        "spread_bps_max": 6.0,
        "atr_bps_min": 1.0,
        "atr_bps_max": 40.0,
        "lag_threshold_pips": 2.0,
        "volume_baseline": 3000.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 20.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 3.0,
        "lead_lag_max_pips": 5.0,
        "arb_min_lag_pips": 3.0,
        "arb_max_lag_pips": 15.0,
        "sl_pips": 50.0,
        "tp_pips": 125.0,
        "session_allow_asia": True,
    },
    "CL": {
        "tick_size": 0.01,
        "pip_size": 0.01,
        "velocity_threshold": 0.05,
        "spread_max_pips": 3.0,
        "spread_bps_max": 5.0,
        "atr_bps_min": 1.0,
        "atr_bps_max": 50.0,
        "lag_threshold_pips": 2.0,
        "volume_baseline": 5000.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 30.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 3.0,
        "lead_lag_max_pips": 5.0,
        "arb_min_lag_pips": 3.0,
        "arb_max_lag_pips": 15.0,
        "sl_pips": 30.0,
        "tp_pips": 75.0,
        "session_allow_asia": False,
    },
}

_SPOT_DEFAULTS: dict[str, dict[str, Any]] = {
    "EURUSD": {
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 2.0,
        "spread_bps_max": 5.0,
        "atr_bps_min": 0.5,
        "atr_bps_max": 30.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 0.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 50.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 1.5,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 5.0,
        "tp_pips": 12.5,
        "session_allow_asia": False,
    },
    "GBPUSD": {
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0004,
        "spread_max_pips": 2.5,
        "spread_bps_max": 5.5,
        "atr_bps_min": 0.6,
        "atr_bps_max": 35.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 0.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 40.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 1.5,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 7.0,
        "tp_pips": 17.5,
        "session_allow_asia": False,
    },
    "USDJPY": {
        "tick_size": 0.001,
        "pip_size": 0.01,
        "velocity_threshold": 0.03,
        "spread_max_pips": 2.5,
        "spread_bps_max": 5.0,
        "atr_bps_min": 0.5,
        "atr_bps_max": 30.0,
        "lag_threshold_pips": 3.0,
        "volume_baseline": 0.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 30.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 2.0,
        "lead_lag_max_pips": 5.0,
        "arb_min_lag_pips": 3.0,
        "arb_max_lag_pips": 15.0,
        "sl_pips": 8.0,
        "tp_pips": 20.0,
        "session_allow_asia": True,
    },
    "AUDUSD": {
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 2.5,
        "spread_bps_max": 5.0,
        "atr_bps_min": 0.5,
        "atr_bps_max": 28.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 0.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 30.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 1.5,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 6.0,
        "tp_pips": 15.0,
        "session_allow_asia": True,
    },
    "USDCAD": {
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 3.0,
        "spread_bps_max": 5.5,
        "atr_bps_min": 0.5,
        "atr_bps_max": 28.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 0.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 30.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 2.0,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 6.0,
        "tp_pips": 15.0,
        "session_allow_asia": False,
    },
    "NZDUSD": {
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 3.0,
        "spread_bps_max": 5.5,
        "atr_bps_min": 0.4,
        "atr_bps_max": 25.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 0.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 25.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 2.0,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 6.0,
        "tp_pips": 15.0,
        "session_allow_asia": True,
    },
    "USDCHF": {
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0003,
        "spread_max_pips": 3.0,
        "spread_bps_max": 5.5,
        "atr_bps_min": 0.5,
        "atr_bps_max": 28.0,
        "lag_threshold_pips": 1.5,
        "volume_baseline": 0.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 30.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 2.0,
        "lead_lag_max_pips": 3.0,
        "arb_min_lag_pips": 2.0,
        "arb_max_lag_pips": 10.0,
        "sl_pips": 6.0,
        "tp_pips": 15.0,
        "session_allow_asia": False,
    },
    "EURSEK": {
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "velocity_threshold": 0.0005,
        "spread_max_pips": 5.0,
        "spread_bps_max": 7.0,
        "atr_bps_min": 0.5,
        "atr_bps_max": 35.0,
        "lag_threshold_pips": 2.0,
        "volume_baseline": 0.0,
        "imbalance_threshold": 0.18,
        "obi_threshold": 0.25,
        "depth_min_contracts": 20.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 3.0,
        "lead_lag_max_pips": 5.0,
        "arb_min_lag_pips": 3.0,
        "arb_max_lag_pips": 15.0,
        "sl_pips": 10.0,
        "tp_pips": 25.0,
        "session_allow_asia": False,
    },
    "XAUUSD": {
        "tick_size": 0.01,
        "pip_size": 0.1,
        "velocity_threshold": 0.5,
        "spread_max_pips": 5.0,
        "spread_bps_max": 6.0,
        "atr_bps_min": 1.0,
        "atr_bps_max": 40.0,
        "lag_threshold_pips": 2.0,
        "volume_baseline": 0.0,
        "imbalance_threshold": 0.15,
        "obi_threshold": 0.2,
        "depth_min_contracts": 20.0,
        "rr_min": 1.5,
        "cross_spread_max_pips": 3.0,
        "lead_lag_max_pips": 5.0,
        "arb_min_lag_pips": 3.0,
        "arb_max_lag_pips": 15.0,
        "sl_pips": 50.0,
        "tp_pips": 125.0,
        "session_allow_asia": True,
    },
}

_GENERIC_PROFILE: dict[str, Any] = {
    "tick_size": 0.0001,
    "pip_size": 0.0001,
    "velocity_threshold": 0.0003,
    "spread_max_pips": 3.0,
    "spread_bps_max": 5.0,
    "atr_bps_min": 0.5,
    "atr_bps_max": 30.0,
    "lag_threshold_pips": 1.5,
    "volume_baseline": 0.0,
    "imbalance_threshold": 0.15,
    "obi_threshold": 0.2,
    "depth_min_contracts": 30.0,
    "rr_min": 1.5,
    "cross_spread_max_pips": 2.0,
    "lead_lag_max_pips": 3.0,
    "arb_min_lag_pips": 2.0,
    "arb_max_lag_pips": 10.0,
    "sl_pips": 5.0,
    "tp_pips": 12.5,
    "session_allow_asia": False,
}

_ATR_WINDOW = 100
_SPREAD_WINDOW = 100
_VELOCITY_WINDOW = 50


class _RollingStats:
    def __init__(self, window: int = _ATR_WINDOW) -> None:
        self._mid_prices: deque[float] = deque(maxlen=window)
        self._spreads: deque[float] = deque(maxlen=_SPREAD_WINDOW)
        self._tick_count: int = 0

    def update(self, bid: float, ask: float) -> None:
        if bid <= 0 or ask <= 0 or ask <= bid:
            return
        mid = (bid + ask) / 2.0
        self._mid_prices.append(mid)
        self._spreads.append(ask - bid)
        self._tick_count += 1

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def rolling_atr_bps(self) -> float | None:
        if len(self._mid_prices) < 20:
            return None
        prices = np.array(self._mid_prices)
        returns = np.diff(prices) / prices[:-1]
        if len(returns) < 2:
            return None
        return float(np.std(returns) * 10000.0)

    def rolling_spread_pips(self, pip_size: float) -> float | None:
        if len(self._spreads) < 10 or pip_size <= 0:
            return None
        return float(np.mean(self._spreads)) / pip_size

    def rolling_velocity(self) -> float | None:
        if len(self._mid_prices) < 5:
            return None
        recent = list(self._mid_prices)
        n = len(recent)
        first_half = recent[: n // 2]
        second_half = recent[n // 2 :]
        if not first_half or not second_half:
            return None
        avg_first = float(np.mean(first_half))
        avg_second = float(np.mean(second_half))
        if avg_first == 0:
            return None
        return (avg_second - avg_first) / avg_first


class InstrumentConfig:
    _instance: InstrumentConfig | None = None

    def __init__(self) -> None:
        self._profiles: dict[str, InstrumentProfile] = {}
        self._rolling: dict[str, _RollingStats] = {}
        self._init_all_profiles()

    @classmethod
    def get_instance(cls) -> InstrumentConfig:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_all_profiles(self) -> None:
        for symbol, defaults in _CME_DEFAULTS.items():
            self._profiles[symbol] = self._build_profile(symbol, defaults)
        for symbol, defaults in _SPOT_DEFAULTS.items():
            self._profiles[symbol] = self._build_profile(symbol, defaults)

    def _build_profile(self, symbol: str, defaults: dict[str, Any]) -> InstrumentProfile:
        overrides = {}
        for fld in InstrumentProfile.__dataclass_fields__:
            env_key = f"INST_{symbol}_{fld.upper()}"
            env_val = os.getenv(env_key)
            if env_val is not None:
                if fld == "session_allow_asia":
                    overrides[fld] = env_val.lower() == "true"
                else:
                    overrides[fld] = float(env_val)
        merged = {**defaults, **overrides}
        merged["symbol"] = symbol
        return InstrumentProfile(**merged)

    def get_profile(self, symbol: str) -> InstrumentProfile:
        if symbol in self._profiles:
            return self._profiles[symbol]
        root = self._resolve_root(symbol)
        if root in self._profiles:
            return self._profiles[root]
        return self._profiles.setdefault(symbol, InstrumentProfile(symbol=symbol, **_GENERIC_PROFILE))

    def _resolve_root(self, symbol: str) -> str:
        if len(symbol) >= 2:
            prefix = symbol[:2]
            if prefix in _CME_DEFAULTS:
                return prefix
        return symbol

    def update_rolling(self, symbol: str, bid: float, ask: float) -> None:
        if symbol not in self._rolling:
            self._rolling[symbol] = _RollingStats()
        self._rolling[symbol].update(bid, ask)

    def enrich_tick(self, tick: dict[str, Any]) -> dict[str, Any]:
        symbol = str(tick.get("symbol", ""))
        profile = self.get_profile(symbol)

        rolling = self._rolling.get(symbol)
        rolling_atr = rolling.rolling_atr_bps() if rolling and rolling.tick_count >= 50 else None
        rolling_spread = rolling.rolling_spread_pips(profile.pip_size) if rolling and rolling.tick_count >= 30 else None
        rolling_vel = rolling.rolling_velocity() if rolling and rolling.tick_count >= 20 else None

        velocity_threshold = profile.velocity_threshold
        if rolling_vel is not None and rolling.tick_count >= 200:
            pass

        atr_bps_min = profile.atr_bps_min
        atr_bps_max = profile.atr_bps_max
        if rolling_atr is not None and rolling.tick_count >= 200:
            atr_bps_min = max(0.1, rolling_atr * 0.3)
            atr_bps_max = rolling_atr * 5.0

        spread_max = profile.spread_max_pips
        if rolling_spread is not None and rolling.tick_count >= 200:
            spread_max = max(spread_max, rolling_spread * 3.0)

        enriched = dict(tick)
        enriched.setdefault("pip_size", profile.pip_size)
        enriched.setdefault("tick_size", profile.tick_size)
        enriched.setdefault("velocity_threshold", velocity_threshold)
        enriched.setdefault("spread_max_pips", spread_max)
        enriched.setdefault("spread_bps_max", profile.spread_bps_max)
        enriched.setdefault("atr_bps_min", atr_bps_min)
        enriched.setdefault("atr_bps_max", atr_bps_max)
        enriched.setdefault("lag_threshold_pips", profile.lag_threshold_pips)
        enriched.setdefault("volume_baseline", profile.volume_baseline)
        enriched.setdefault("imbalance_threshold", profile.imbalance_threshold)
        enriched.setdefault("obi_threshold", profile.obi_threshold)
        enriched.setdefault("depth_min_contracts", profile.depth_min_contracts)
        enriched.setdefault("risk_reward_min", profile.rr_min)
        enriched.setdefault("cross_spread_max_pips", profile.cross_spread_max_pips)
        enriched.setdefault("lead_lag_max_pips", profile.lead_lag_max_pips)
        enriched.setdefault("arb_min_lag_pips", profile.arb_min_lag_pips)
        enriched.setdefault("arb_max_lag_pips", profile.arb_max_lag_pips)
        enriched.setdefault("sl_pips", profile.sl_pips)
        enriched.setdefault("tp_pips", profile.tp_pips)
        enriched.setdefault("session_allow_asia", profile.session_allow_asia)

        if rolling_atr is not None:
            enriched.setdefault("rolling_atr_bps", rolling_atr)
        if rolling_spread is not None:
            enriched.setdefault("rolling_spread_pips", rolling_spread)

        return enriched

    def get_all_profiles(self) -> dict[str, InstrumentProfile]:
        return dict(self._profiles)
