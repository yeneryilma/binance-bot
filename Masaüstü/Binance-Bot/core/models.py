from dataclasses import dataclass
from typing import Optional

@dataclass
class Signal:
    symbol: str
    direction: Optional[str]
    price: float = 0.0
    stop: float = 0.0
    take_profit: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    willr: float = 0.0
    stoch_k: float = 0.0
    stoch_d: float = 0.0
    rsi: float = 0.0
    ema_trend: str = "N/A"
    vol_ratio: float = 0.0
    strength: str = "Normal"
