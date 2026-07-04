"""Framework Score Aggregator for OVERSEER v12.10.

Collapses 141+ individual binary gate outputs into 19 framework-level
continuous scores (0.0 – 1.0). This dramatically reduces the feature
space fed to XGBoost, preventing overfit and making the model actually
learnable from small sample sizes.

Framework mapping:
FW01 Multi-TF Trend Alignment gate_A + gate_B gates
FW02 Price Action / Wick Rejection gate_C + gate_E + gate_SR
FW03 Volume Confirmation gate_F + gate_G + gate_VOL + gate_DD + gate_IMB + gate_CVD
FW04 Liquidity Sweep gate_H + gate_I
FW05 Weekly Level Proximity gate_J + gate_K
FW06 Session / Kill Zone gate_SESSION + gate_L + gate_M
FW07 Economic Event Lean gate_NEWS + gate_N + gate_O
FW08 Asian Range Breakout gate_P + gate_Q
FW09 COT Positioning gate_R + gate_S
FW10 Post-News Continuation gate_T + gate_U
FW11 Options IV / Skew gate_IVSKEW + gate_IVEXP
FW12 DXY / Cross-Pair Isolation gate_DXY + gate_V + gate_W
FW13 Lag Arbitrage gate_XMKT + gate_LEADLAG + gate_ARB + gate_XCORR
FW14 Risk Regime gate_REGIME + gate_X + gate_Y
FW15 L3 Institutional Flow gate_Z + gate_Z1-Z7 core subset
FW16 Directional Momentum gate_D
FW17 Volume Profile / Market Structure gate_VP + gate_TPO + gate_VWAP + gate_stacked_imbalance + gate_iceberg_monitor
FW18 Technical Analysis gate_RSI + gate_MACD + gate_BB + gate_bar_cot
FW19 Fundamental Alignment gate_FUND

Directional Asymmetry: SELL signals require stricter thresholds.
BUY signals use default weights. SELL signals get a 0.6 multiplier
on framework scores to reflect the quantile regression finding that
selling pressure is diluted by institutional hedging.

Each framework score is a float in [0.0, 1.0] representing how many
of its component gates passed, weighted by importance.
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger("overseer.framework_scorer")

_FRAMEWORK_MAP: dict[str, dict[str, float]] = {
    "FW01_multi_tf_trend": {
        "gate_A": 1.0, "gate_B": 1.0,
    },
    "FW02_price_action": {
        "gate_C": 1.0, "gate_E": 1.0, "gate_SR": 0.5,
    },
    "FW03_volume": {
        "gate_F": 1.0, "gate_G": 1.0, "gate_VOL": 1.5,
        "gate_DD": 0.5, "gate_IMB": 0.5, "gate_CVD": 0.5,
    },
    "FW04_liquidity_sweep": {
        "gate_H": 1.0, "gate_I": 1.0,
        "gate_Z14": 0.3, "gate_Z15": 0.3, "gate_Z16": 0.3,
    },
    "FW05_weekly_levels": {
        "gate_J": 1.0, "gate_K": 1.0,
    },
    "FW06_session_kz": {
        "gate_SESSION": 1.5, "gate_L": 1.0, "gate_M": 1.0,
    },
    "FW07_econ_event": {
        "gate_NEWS": 1.5, "gate_N": 1.0, "gate_O": 1.0,
    },
    "FW08_asian_range": {
        "gate_P": 1.0, "gate_Q": 1.0,
    },
    "FW09_cot_positioning": {
        "gate_R": 1.0, "gate_S": 1.0,
    },
    "FW10_post_news": {
        "gate_T": 1.0, "gate_U": 1.0,
    },
    "FW11_iv_skew": {
        "gate_IVSKEW": 1.5, "gate_IVEXP": 1.0,
    },
    "FW12_dxy_isolation": {
        "gate_DXY": 1.5, "gate_V": 1.0, "gate_W": 1.0,
    },
    "FW13_lag_arb": {
        "gate_XMKT": 1.0, "gate_LEADLAG": 1.5, "gate_ARB": 1.0, "gate_XCORR": 1.0,
    },
    "FW14_risk_regime": {
        "gate_REGIME": 1.5, "gate_X": 1.0, "gate_Y": 1.0,
    },
    "FW15_l3_flow": {
        "gate_Z": 1.0, "gate_Z1": 0.5, "gate_Z2": 0.5, "gate_Z3": 0.5,
        "gate_Z4": 0.5, "gate_Z5": 0.5, "gate_Z6": 0.5, "gate_Z7": 1.0,
        "gate_Z8": 0.2, "gate_Z9": 0.3, "gate_Z10": 0.2, "gate_Z11": 0.2,
        "gate_Z12": 0.2, "gate_Z13": 0.2,
        **{f"gate_Z{i}": 0.05 for i in range(17, 95)},
    },
    "FW16_directional_momentum": {
        "gate_D": 1.5,
    },
    "FW17_volume_profile": {
        "gate_VP": 1.5, "gate_TPO": 1.0, "gate_VWAP": 1.0,
        "gate_stacked_imbalance": 1.0, "gate_iceberg_monitor": 0.8,
        "gate_tape_velocity": 0.5, "gate_HURST": 0.8,
    },
    "FW18_technical": {
        "gate_RSI": 1.0, "gate_MACD": 1.0, "gate_BB": 1.0,
        "gate_bar_cot": 0.8, "gate_unfinished": 0.5,
    },
    "FW19_fundamental": {
        "gate_FUND": 1.5,
    },
    "FW20_legendary": {
        "gate_Z15": 1.5, "gate_A": 1.0, "gate_D": 1.0,
        "gate_stacked_imbalance": 0.8, "gate_CVD": 0.8, "gate_M": 1.0,
        "gate_legendary_composite": 2.0,
    },
    "FW21_smart_money": {
        "gate_FVG": 1.2, "gate_ORDER_BLOCK": 1.2, "gate_SFP": 1.0,
        "gate_WYCKOFF": 1.0, "gate_PO3": 1.0,
        "gate_stacked_imbalance": 0.8, "gate_iceberg_monitor": 0.8,
        "gate_CVD": 0.6, "gate_unfinished": 0.6,
    },
    "FW22_intermarket": {
        "gate_DXY": 1.0, "gate_V": 1.0, "gate_W": 1.0,
        "gate_XMKT": 0.8, "gate_LEADLAG": 0.8,
        "gate_DXY_TREND": 1.2, "gate_CURRENCY_STR": 1.0, "gate_LONDON_FIX": 0.8,
    },
    "FW23_positioning": {
        "gate_R": 1.0, "gate_S": 1.0, "gate_FUND": 0.8,
        "gate_Z14": 0.5, "gate_Z15": 0.5,
        "gate_RETAIL_SENTIMENT": 1.2, "gate_GAMMA_EXPOSURE": 1.0,
    },
}


def aggregate_framework_scores(gate_states: dict[str, bool], direction: str = "BUY") -> dict[str, float]:
    """Collapse binary gate outputs into 19 framework-level continuous scores.

    Parameters
    ----------
    gate_states : dict
        Gate name → bool (True = passed).
    direction : str
        "BUY" or "SELL". SELL scores are penalized by 0.6 multiplier
        to reflect quantile regression asymmetry.

    Returns
    -------
    dict
        19 framework scores, each in [0.0, 1.0].
    """
    sell_multiplier = 0.6 if direction == "SELL" else 1.0
    scores: dict[str, float] = {}

    for fw_name, gate_weights in _FRAMEWORK_MAP.items():
        total_weight = sum(gate_weights.values())
        if total_weight == 0:
            scores[fw_name] = 0.0
            continue

        earned_weight = 0.0
        for gate_name, weight in gate_weights.items():
            if gate_states.get(gate_name, False):
                earned_weight += weight

        raw_score = earned_weight / total_weight
        scores[fw_name] = round(raw_score * sell_multiplier, 4)

    return scores


def framework_scores_to_vector(scores: dict[str, float]) -> list[float]:
    """Return the 19 framework scores as a fixed-order list."""
    return [scores.get(fw, 0.0) for fw in sorted(_FRAMEWORK_MAP.keys())]


def get_framework_feature_names() -> list[str]:
    """Return the ordered list of framework feature names."""
    return sorted(_FRAMEWORK_MAP.keys())
