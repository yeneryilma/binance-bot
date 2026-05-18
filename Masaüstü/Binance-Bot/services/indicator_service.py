import numpy as np
import pandas as pd
from config import Config

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    cfg = Config.CONFIG
    C, H, L = df['Close'], df['High'], df['Low']

    tr = pd.concat([
        (H - L),
        (H - C.shift(1)).abs(),
        (L - C.shift(1)).abs()
    ], axis=1).max(axis=1)

    df['ATR'] = tr.ewm(span=cfg['atr_span'], adjust=False).mean()
    df['ATR_MA'] = df['ATR'].rolling(cfg['atr_ma_period']).mean()

    delta = C.diff()
    gain = delta.clip(lower=0).ewm(span=cfg['rsi_span'], adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=cfg['rsi_span'], adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + gain / (loss + 1e-10)))

    hw = H.rolling(cfg['willr_window']).max()
    lw = L.rolling(cfg['willr_window']).min()
    df['WILLR'] = -100 * (hw - C) / (hw - lw + 1e-10)

    hn = H.rolling(cfg['stoch_k']).max()
    ln = L.rolling(cfg['stoch_k']).min()
    df['STOCH_K'] = 100 * (C - ln) / (hn - ln + 1e-10)
    df['STOCH_D'] = df['STOCH_K'].rolling(cfg['stoch_d']).mean()

    df['EMA_FAST'] = C.ewm(span=cfg['ema_fast'], adjust=False).mean()
    df['EMA_SLOW'] = C.ewm(span=cfg['ema_slow'], adjust=False).mean()

    df['VOL_MA'] = df['Volume'].rolling(cfg['vol_ma_period']).mean()
    df['VOL_RATIO'] = df['Volume'] / (df['VOL_MA'] + 1e-10)

    ema_fast_macd = C.ewm(span=cfg['macd_fast'], adjust=False).mean()
    ema_slow_macd = C.ewm(span=cfg['macd_slow'], adjust=False).mean()
    df['MACD'] = ema_fast_macd - ema_slow_macd
    df['MACD_SIGNAL'] = df['MACD'].ewm(span=cfg['macd_signal'], adjust=False).mean()
    df['MACD_HIST'] = df['MACD'] - df['MACD_SIGNAL']

    df['BB_MID'] = C.rolling(cfg['bb_period']).mean()
    df['BB_STD'] = C.rolling(cfg['bb_period']).std()
    df['BB_UPPER'] = df['BB_MID'] + cfg['bb_std'] * df['BB_STD']
    df['BB_LOWER'] = df['BB_MID'] - cfg['bb_std'] * df['BB_STD']
    df['BB_WIDTH'] = (df['BB_UPPER'] - df['BB_LOWER']) / (df['BB_MID'] + 1e-10)

    df['OBV'] = (np.sign(C.diff()) * df['Volume']).fillna(0).cumsum()
    df['OBV_EMA'] = df['OBV'].ewm(span=cfg['obv_ema_span'], adjust=False).mean()

    df['ROC'] = C.pct_change(cfg['roc_period']) * 100
    return df

def get_htf_trend(symbol: str, fetch_klines_func) -> str:
    cfg    = Config.CONFIG
    period = cfg.get('ema_htf_period', 28)
    if not isinstance(period,int) or period < 1:
        period=28

    df = fetch_klines_func(symbol, interval=cfg['interval_confirm'], limit=100)
    if df is None or len(df) < period:
        return 'FLAT'

    C   = df['Close']
    ema = C.ewm(span=period, adjust=False).mean()

    price = float(C.iloc[-2])
    emav  = float(ema.iloc[-2])

    if price > emav:
        return 'UP'
    if price < emav:
        return 'DOWN'

    return 'FLAT'
