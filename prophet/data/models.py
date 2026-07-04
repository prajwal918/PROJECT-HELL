from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal


@dataclass
class Candle:
    timestamp:  datetime
    open:       float
    high:       float
    low:        float
    close:      float
    volume:     float
    asset:      str
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    delta:      float = 0.0
    imbalance_ratio: float = 0.0
    iceberg_reloads: int = 0
    orderid_depth: float = 0.0
    l3_flow_score: float = 0.0
    mbo_events: int = 0

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2


@dataclass
class VolumeProfile:
    vah:        float           # Value Area High
    val:        float           # Value Area Low
    poc:        float           # Point of Control
    value_area_volume: float    # 70% of total volume


@dataclass
class SignalResult:
    timestamp:          datetime
    asset:              str
    direction:          Optional[Literal["UP", "DOWN"]]   # None = NO TRADE
    confidence:         float           # 0.0 to 1.0
    at_key_level:       bool
    key_level_type:     Optional[str]   # "VAH", "VAL", "POC"
    current_price:      float
    cvd_value:          float
    volume_zscore:      float
    phase1_pass:        bool
    phase2_pass:        bool
    phase3_pass:        bool
    reason:             str             # human-readable explanation


@dataclass
class TradeRecord:
    id:             Optional[int]
    timestamp:      datetime
    asset:          str
    direction:      str
    stake:          float
    duration:       int
    signal:         SignalResult
    broker_trade_id: Optional[str]
    result:         Optional[Literal["WIN", "LOSS", "TIE"]]
    profit:         Optional[float]
    demo:           bool
