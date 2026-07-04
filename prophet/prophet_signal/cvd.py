from __future__ import annotations

from typing import List
from data.models import Candle


def calculate_cvd(candles: List[Candle], window: int = 20) -> List[float]:
    """
    Pseudo-Cumulative Volume Delta.
    Uses candle body direction × volume as a proxy for buy/sell pressure.
    """
    if len(candles) < 2:
        return [0.0]

    recent = candles[-window:]
    cvd_series = []
    running = 0.0

    for candle in recent:
        if getattr(candle, "delta", 0.0):
            delta = candle.delta
        else:
            body_ratio = (candle.close - candle.open) / (candle.high - candle.low + 1e-10)
            delta = body_ratio * candle.volume
        running += delta
        cvd_series.append(running)

    return cvd_series


def get_cvd_divergence(candles: List[Candle], window: int = 10) -> float:
    """
    Detects CVD divergence: price making lower lows while CVD stops falling.
    """
    if len(candles) < window:
        return 0.0

    recent = candles[-window:]
    cvd_series = calculate_cvd(recent, window)

    price_change = (recent[-1].close - recent[0].close) / (recent[0].close + 1e-10)

    if len(cvd_series) < 2:
        return 0.0
    cvd_change = (cvd_series[-1] - cvd_series[0]) / (abs(cvd_series[0]) + 1e-10)

    divergence = price_change - cvd_change
    return float(divergence)


def is_cvd_reversing(candles: List[Candle], lookback: int = 5) -> bool:
    """
    Returns True if CVD was falling but has now ticked upward.
    """
    cvd = calculate_cvd(candles, window=lookback + 5)
    if len(cvd) < lookback + 1:
        return False

    was_falling = cvd[-lookback] > cvd[-3]
    now_rising  = cvd[-1] > cvd[-2]

    return was_falling and now_rising
