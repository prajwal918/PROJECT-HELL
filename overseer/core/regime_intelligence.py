"""Institutional Regime Detection Engine.

Gaussian Mixture Model (GMM) for unsupervised regime discovery.
Hidden Markov Model (HMM) for regime transition prediction.
GARCH(1,1) for volatility regime detection.
Change-Point Detection (CUSUM) for structural break identification.
Kalman Filter for smooth regime tracking.

Replaces the simple 3-state VIX-threshold classifier with a data-driven
multi-dimensional regime system that discovers regimes from the actual
CME futures microstructure data.

Regime dimensions (not just risk_on/off):
- Volatility: calm / normal / volatile / extreme
- Trend: mean-reverting / ranging / trending
- Liquidity: deep / normal / thin / crisis
- Microstructure: retail-dominated / mixed / institutional
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.regime_intel")

REGIME_HISTORY_LEN = int(os.getenv("REGIME_HISTORY_LEN", "500"))
GARCH_OMEGA = float(os.getenv("GARCH_OMEGA", "0.00001"))
GARCH_ALPHA = float(os.getenv("GARCH_ALPHA", "0.10"))
GARCH_BETA = float(os.getenv("GARCH_BETA", "0.85"))
CUSUM_THRESHOLD = float(os.getenv("CUSUM_THRESHOLD", "3.0"))
CUSUM_DRIFT = float(os.getenv("CUSUM_DRIFT", "0.5"))
KALMAN_Q = float(os.getenv("KALMAN_Q", "0.001"))
KALMAN_R = float(os.getenv("KALMAN_R", "0.01"))
N_REGIMES_GMM = int(os.getenv("N_REGIMES_GMM", "5"))
MIN_WARMUP = int(os.getenv("REGIME_MIN_WARMUP", "100"))
RETRAIN_INTERVAL = int(os.getenv("REGIME_RETRAIN_INTERVAL", "500"))


class GARCH11:
    """GARCH(1,1) volatility model per symbol."""

    def __init__(self) -> None:
        self.omega = GARCH_OMEGA
        self.alpha = GARCH_ALPHA
        self.beta = GARCH_BETA
        self.sigma2: float = 0.0
        self._initialized = False
        self._returns: deque[float] = deque(maxlen=REGIME_HISTORY_LEN)

    def update(self, return_value: float) -> float:
        self._returns.append(return_value)
        if not self._initialized:
            if len(self._returns) >= 20:
                self.sigma2 = float(np.var(list(self._returns)))
                self._initialized = True
            return self.sigma2
        self.sigma2 = self.omega + self.alpha * return_value ** 2 + self.beta * self.sigma2
        return self.sigma2

    def conditional_vol(self) -> float:
        return math.sqrt(max(0, self.sigma2))

    def vol_regime(self) -> str:
        vol = self.conditional_vol()
        returns = list(self._returns)
        if len(returns) < 50:
            return "unknown"
        realized = float(np.std(returns))
        if vol < realized * 0.5:
            return "calm"
        elif vol < realized:
            return "normal"
        elif vol < realized * 2:
            return "volatile"
        else:
            return "extreme"


class CUSUMDetector:
    """CUSUM change-point detector."""

    def __init__(self) -> None:
        self.threshold = CUSUM_THRESHOLD
        self.drift = CUSUM_DRIFT
        self._positive: float = 0.0
        self._negative: float = 0.0
        self._mean: float = 0.0
        self._count: int = 0
        self._change_points: list[int] = []
        self._total_observations: int = 0

    def update(self, value: float) -> bool:
        self._total_observations += 1
        self._count += 1
        self._mean += (value - self._mean) / self._count
        deviation = value - self._mean - self.drift
        self._positive = max(0, self._positive + deviation)
        self._negative = min(0, self._negative - deviation)
        if self._positive > self.threshold or self._negative < -self.threshold:
            self._positive = 0.0
            self._negative = 0.0
            self._change_points.append(self._total_observations)
            return True
        return False

    def get_change_points(self) -> list[int]:
        return list(self._change_points)

    def recent_change(self, window: int = 50) -> bool:
        if not self._change_points:
            return False
        return (self._total_observations - self._change_points[-1]) < window


class KalmanRegimeTracker:
    """1D Kalman filter for smooth regime state tracking."""

    def __init__(self) -> None:
        self.x: float = 0.0
        self.P: float = 1.0
        self.Q = KALMAN_Q
        self.R = KALMAN_R

    def update(self, measurement: float) -> float:
        self.P = self.P + self.Q
        K = self.P / (self.P + self.R)
        self.x = self.x + K * (measurement - self.x)
        self.P = (1 - K) * self.P
        return self.x

    def get_state(self) -> float:
        return self.x


class SimpleGMM:
    """Lightweight GMM for regime clustering. No sklearn dependency."""

    def __init__(self, n_components: int = N_REGIMES_GMM) -> None:
        self.n_components = n_components
        self.means: np.ndarray | None = None
        self.covs: list[float] = []
        self.weights: np.ndarray | None = None
        self._fitted = False

    def fit(self, data: np.ndarray, max_iter: int = 30) -> None:
        if len(data) < self.n_components * 10:
            return
        n = len(data)
        k = self.n_components
        data_sorted = np.sort(data)
        quantiles = np.linspace(0, 100, k + 2)[1:-1]
        self.means = np.percentile(data_sorted, quantiles)
        self.covs = [float(np.var(data)) / k] * k
        self.weights = np.ones(k) / k
        for _ in range(max_iter):
            resp = np.zeros((n, k))
            for j in range(k):
                if self.covs[j] > 1e-12:
                    resp[:, j] = (
                        self.weights[j]
                        * np.exp(-0.5 * (data - self.means[j]) ** 2 / self.covs[j])
                        / math.sqrt(2 * math.pi * self.covs[j])
                    )
                else:
                    resp[:, j] = self.weights[j] * 1e-10
            resp_sum = resp.sum(axis=1, keepdims=True)
            resp_sum = np.maximum(resp_sum, 1e-10)
            resp = resp / resp_sum
            for j in range(k):
                nj = resp[:, j].sum()
                if nj > 1e-10:
                    self.means[j] = (resp[:, j] * data).sum() / nj
                    diff = data - self.means[j]
                    self.covs[j] = max(1e-12, float((resp[:, j] * diff ** 2).sum() / nj))
                    self.weights[j] = nj / n
        self._fitted = True

    def predict(self, value: float) -> int:
        if not self._fitted or self.means is None:
            return 0
        dists = [(value - self.means[j]) ** 2 / max(1e-12, self.covs[j]) for j in range(self.n_components)]
        return int(np.argmin(dists))

    def predict_proba(self, value: float) -> np.ndarray:
        if not self._fitted or self.means is None:
            return np.ones(self.n_components) / self.n_components
        probs = np.zeros(self.n_components)
        for j in range(self.n_components):
            if self.covs[j] > 1e-12:
                probs[j] = self.weights[j] * np.exp(-0.5 * (value - self.means[j]) ** 2 / self.covs[j])
            else:
                probs[j] = self.weights[j] * 1e-10
        total = probs.sum()
        return probs / total if total > 1e-10 else np.ones(self.n_components) / self.n_components


class SimpleHMM:
    """Lightweight Hidden Markov Model for regime transitions.

    Discrete observation HMM with Baum-Welch training.
    Observations are quantized regime labels from GMM.
    """

    def __init__(self, n_states: int = 4) -> None:
        self.n_states = n_states
        self.A = np.ones((n_states, n_states)) / n_states
        self.B = np.ones((n_states, n_states)) / n_states
        self.pi = np.ones(n_states) / n_states
        self._fitted = False
        self._last_state: int = 0
        self._state_history: deque[int] = deque(maxlen=REGIME_HISTORY_LEN)

    def fit(self, observations: list[int], max_iter: int = 20) -> None:
        if len(observations) < 50:
            return
        n = self.n_states
        self.A = np.ones((n, n)) * 0.01 + np.eye(n) * 0.9
        self.A /= self.A.sum(axis=1, keepdims=True)
        self.B = np.ones((n, n)) / n
        self.pi = np.ones(n) / n
        seq = np.array(observations)
        for _ in range(max_iter):
            alpha = np.zeros((len(seq), n))
            for i in range(n):
                alpha[0, i] = self.pi[i] * self.B[i, min(seq[0], n - 1)]
            for t in range(1, len(seq)):
                obs = min(seq[t], n - 1)
                for j in range(n):
                    alpha[t, j] = self.B[j, obs] * (alpha[t - 1] * self.A[:, j]).sum()
            beta = np.zeros((len(seq), n))
            beta[-1] = 1.0
            for t in range(len(seq) - 2, -1, -1):
                obs = min(seq[t + 1], n - 1)
                for i in range(n):
                    beta[t, i] = (self.A[i] * self.B[:, obs] * beta[t + 1]).sum()
            gamma = alpha * beta
            gamma_sum = gamma.sum(axis=1, keepdims=True)
            gamma = gamma / np.maximum(gamma_sum, 1e-10)
            self.pi = gamma[0]
            for i in range(n):
                for j in range(n):
                    num = 0.0
                    den = 0.0
                    for t in range(len(seq) - 1):
                        obs = min(seq[t + 1], n - 1)
                        xi = alpha[t, i] * self.A[i, j] * self.B[j, obs] * beta[t + 1, j]
                        num += xi
                        den += gamma[t, i]
                    self.A[i, j] = num / max(den, 1e-10)
            for i in range(n):
                for k in range(n):
                    mask = (seq == k)
                    self.B[i, k] = gamma[mask, i].sum() / max(gamma[:, i].sum(), 1e-10)
            self.A = np.maximum(self.A, 1e-6)
            self.A /= self.A.sum(axis=1, keepdims=True)
            self.B = np.maximum(self.B, 1e-6)
            self.B /= self.B.sum(axis=1, keepdims=True)
        self._fitted = True

    def predict_next(self, current_state: int | None = None) -> tuple[int, np.ndarray]:
        s = current_state if current_state is not None else self._last_state
        transition_probs = self.A[s]
        next_state = int(np.argmax(transition_probs))
        return next_state, transition_probs

    def update(self, observation: int) -> None:
        self._last_state = observation
        self._state_history.append(observation)

    def get_transition_matrix(self) -> np.ndarray:
        return self.A.copy()

    def regime_persistence(self) -> float:
        if not self._fitted:
            return 0.0
        return float(np.mean(np.diag(self.A)))


class RegimeIntelEngine:
    """Multi-symbol, multi-dimensional institutional regime engine.

    Combines GARCH, CUSUM, Kalman, GMM, and HMM into a single
    regime intelligence system that feeds directly into gate evaluation
    and dynamic thresholds.

    Usage:
        engine = RegimeIntelEngine()
        engine.on_tick("6EM6", mid_price, spread_bps, depth, ofi)
        regime = engine.get_regime("6EM6")
        # regime = {"vol_regime": "calm", "trend_regime": "trending", ...}
    """

    def __init__(self) -> None:
        self._garch: dict[str, GARCH11] = {}
        self._cusum: dict[str, CUSUMDetector] = {}
        self._cusum_vol: dict[str, CUSUMDetector] = {}
        self._kalman_vol: dict[str, KalmanRegimeTracker] = {}
        self._kalman_liq: dict[str, KalmanRegimeTracker] = {}
        self._gmm_vol: SimpleGMM = SimpleGMM(N_REGIMES_GMM)
        self._gmm_liq: SimpleGMM = SimpleGMM(N_REGIMES_GMM)
        self._hmm: SimpleHMM = SimpleHMM(4)
        self._mid_history: dict[str, deque[float]] = {}
        self._spread_history: dict[str, deque[float]] = {}
        self._depth_history: dict[str, deque[float]] = {}
        self._ofi_history: dict[str, deque[float]] = {}
        self._tick_count: int = 0
        self._regime_cache: dict[str, dict[str, Any]] = {}

    def on_tick(self, symbol: str, mid: float, spread_bps: float = 0.0, depth: float = 0.0, ofi: float = 0.0) -> dict[str, Any]:
        self._tick_count += 1
        if symbol not in self._mid_history:
            self._mid_history[symbol] = deque(maxlen=REGIME_HISTORY_LEN)
            self._spread_history[symbol] = deque(maxlen=REGIME_HISTORY_LEN)
            self._depth_history[symbol] = deque(maxlen=REGIME_HISTORY_LEN)
            self._ofi_history[symbol] = deque(maxlen=REGIME_HISTORY_LEN)
            self._garch[symbol] = GARCH11()
            self._cusum[symbol] = CUSUMDetector()
            self._cusum_vol[symbol] = CUSUMDetector()
            self._kalman_vol[symbol] = KalmanRegimeTracker()
            self._kalman_liq[symbol] = KalmanRegimeTracker()
        prev_mid = self._mid_history[symbol][-1] if self._mid_history[symbol] else mid
        ret = (mid - prev_mid) / prev_mid if prev_mid > 0 else 0.0
        self._mid_history[symbol].append(mid)
        self._spread_history[symbol].append(spread_bps)
        self._depth_history[symbol].append(depth)
        self._ofi_history[symbol].append(ofi)
        self._garch[symbol].update(ret)
        self._cusum[symbol].update(ret)
        self._cusum_vol[symbol].update(spread_bps)
        self._kalman_vol[symbol].update(spread_bps)
        self._kalman_liq[symbol].update(depth)
        if self._tick_count % RETRAIN_INTERVAL == 0:
            self._retrain_models()
        regime = self._compute_regime(symbol)
        self._regime_cache[symbol] = regime
        return regime

    def _retrain_models(self) -> None:
        all_vols = []
        all_depths = []
        for sym in self._spread_history:
            all_vols.extend(list(self._spread_history[sym]))
            all_depths.extend(list(self._depth_history[sym]))
        if len(all_vols) >= MIN_WARMUP:
            self._gmm_vol.fit(np.array(all_vols))
        if len(all_depths) >= MIN_WARMUP:
            self._gmm_liq.fit(np.array(all_depths))
        all_obs = []
        for sym in self._mid_history:
            mids = list(self._mid_history[sym])
            if len(mids) < 20:
                continue
            rets = np.diff(mids) / np.array(mids[:-1])
            rets = rets[~np.isnan(rets) & ~np.isinf(rets)]
            if len(rets) > 10:
                self._gmm_vol.fit(rets)
                for r in rets:
                    all_obs.append(self._gmm_vol.predict(r))
        if len(all_obs) >= MIN_WARMUP:
            self._hmm.fit(all_obs)

    def _compute_regime(self, symbol: str) -> dict[str, Any]:
        vol_regime = self._garch.get(symbol, GARCH11()).vol_regime() if symbol in self._garch else "unknown"
        trend_regime = self._compute_trend_regime(symbol)
        liq_regime = self._compute_liquidity_regime(symbol)
        micro_regime = self._compute_microstructure_regime(symbol)
        change_point = self._cusum.get(symbol, CUSUMDetector()).recent_change(50)
        vol_change = self._cusum_vol.get(symbol, CUSUMDetector()).recent_change(50)
        kalman_vol = self._kalman_vol.get(symbol, KalmanRegimeTracker()).get_state() if symbol in self._kalman_vol else 0.0
        kalman_liq = self._kalman_liq.get(symbol, KalmanRegimeTracker()).get_state() if symbol in self._kalman_liq else 0.0
        hmm_next, hmm_probs = self._hmm.predict_next()
        composite = self._compute_composite_regime(vol_regime, trend_regime, liq_regime, micro_regime)
        return {
            "vol_regime": vol_regime,
            "trend_regime": trend_regime,
            "liquidity_regime": liq_regime,
            "microstructure_regime": micro_regime,
            "composite_regime": composite,
            "change_point_detected": change_point,
            "vol_change_detected": vol_change,
            "garch_cond_vol": self._garch[symbol].conditional_vol() if symbol in self._garch else 0.0,
            "kalman_vol": round(kalman_vol, 4),
            "kalman_liq": round(kalman_liq, 4),
            "hmm_next_state": hmm_next,
            "hmm_transition_probs": [round(float(p), 4) for p in hmm_probs],
            "hmm_regime_persistence": round(self._hmm.regime_persistence(), 4),
            "regime_stability": "stable" if not change_point and not vol_change else "transitioning",
            "trade_allowed": composite in ("calm_trending_deep_institutional", "normal_trending_deep_institutional", "normal_ranging_normal_mixed"),
        }

    def _compute_trend_regime(self, symbol: str) -> str:
        mids = list(self._mid_history.get(symbol, []))
        if len(mids) < 50:
            return "unknown"
        recent = np.array(mids[-50:])
        x = np.arange(len(recent))
        slope = np.polyfit(x, recent, 1)[0]
        std = np.std(recent)
        if std > 0:
            t_stat = abs(slope) / (std / math.sqrt(len(recent)))
        else:
            t_stat = 0
        if t_stat > 3.0:
            return "trending"
        elif t_stat > 1.5:
            return "ranging"
        else:
            return "mean_reverting"

    def _compute_liquidity_regime(self, symbol: str) -> str:
        depths = list(self._depth_history.get(symbol, []))
        if len(depths) < 30:
            return "unknown"
        recent = depths[-30:]
        mean_depth = float(np.mean(recent))
        std_depth = float(np.std(recent))
        current = recent[-1]
        if std_depth > 0:
            z = (current - mean_depth) / std_depth
        else:
            z = 0
        if z > 1.0:
            return "deep"
        elif z > -1.0:
            return "normal"
        elif z > -2.0:
            return "thin"
        else:
            return "crisis"

    def _compute_microstructure_regime(self, symbol: str) -> str:
        ofis = list(self._ofi_history.get(symbol, []))
        if len(ofis) < 30:
            return "unknown"
        recent = ofis[-30:]
        ofi_std = float(np.std(recent))
        ofi_mean = float(np.mean([abs(o) for o in recent]))
        if ofi_std > ofi_mean * 2:
            return "institutional"
        elif ofi_std > ofi_mean:
            return "mixed"
        else:
            return "retail_dominated"

    def _compute_composite_regime(self, vol: str, trend: str, liq: str, micro: str) -> str:
        return f"{vol}_{trend}_{liq}_{micro}"

    def get_regime(self, symbol: str) -> dict[str, Any]:
        return self._regime_cache.get(symbol, {"composite_regime": "unknown", "trade_allowed": True})

    def get_all_regimes(self) -> dict[str, dict[str, Any]]:
        return dict(self._regime_cache)

    def get_status(self) -> dict[str, Any]:
        return {
            "symbols": list(self._regime_cache.keys()),
            "tick_count": self._tick_count,
            "hmm_fitted": self._hmm._fitted,
            "gmm_vol_fitted": self._gmm_vol._fitted,
            "gmm_liq_fitted": self._gmm_liq._fitted,
        }
