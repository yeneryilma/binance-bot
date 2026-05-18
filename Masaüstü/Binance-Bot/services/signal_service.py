import pandas as pd
from config import Config, STRENGTH_ORDER

def get_signal(df: pd.DataFrame):
    if len(df) < 6:
        return {'direction': None}

    cfg = Config.CONFIG

    row = df.iloc[-2]
    prev = df.iloc[-3]
    prev2 = df.iloc[-4]

    W, W_prev, W_prev2 = float(row['WILLR']), float(prev['WILLR']), float(prev2['WILLR'])
    SK, SK_prev = float(row['STOCH_K']), float(prev['STOCH_K'])
    SD = float(row['STOCH_D'])
    RSI = float(row['RSI'])
    ATR = float(row['ATR'])
    ATR_MA = float(row['ATR_MA'])
    price = float(row['Close'])
    EMA_F = float(row['EMA_FAST'])
    EMA_S = float(row['EMA_SLOW'])
    VOL_RATIO = float(row['VOL_RATIO'])

    MACD = float(row['MACD'])
    MACD_SIGNAL = float(row['MACD_SIGNAL'])
    BB_UPPER = float(row['BB_UPPER'])
    BB_LOWER = float(row['BB_LOWER'])
    BB_WIDTH = float(row['BB_WIDTH'])
    BB_WIDTH_MA = float(df['BB_WIDTH'].rolling(50).mean().iloc[-2]) if not pd.isna(df['BB_WIDTH'].rolling(50).mean().iloc[-2]) else BB_WIDTH
    OBV = float(row['OBV'])
    OBV_EMA = float(row['OBV_EMA'])
    ROC = float(row['ROC']) if not pd.isna(row['ROC']) else 0.0

    if price <= 0 or ATR <= 0:
        return {'direction': None}

    atr_pct = ATR / price
    if atr_pct < cfg['min_atr_pct']:
        return {'direction': None}

    if cfg['use_two_candle_confirm']:
        wr_long = (W_prev2 < cfg['willr_os']) and (W_prev < cfg['willr_os']) and (W >= cfg['willr_os'])
        wr_short = (W_prev2 > cfg['willr_ob']) and (W_prev > cfg['willr_ob']) and (W <= cfg['willr_ob'])
    else:
        wr_long = (W_prev < cfg['willr_os']) and (W >= cfg['willr_os'])
        wr_short = (W_prev > cfg['willr_ob']) and (W <= cfg['willr_ob'])

    st_long = (SK_prev < cfg['stoch_os']) and (SK >= cfg['stoch_os']) and (SK > SD)
    st_short = (SK_prev > cfg['stoch_ob']) and (SK <= cfg['stoch_ob']) and (SK < SD)

    rsi_long_ok = RSI < cfg['rsi_ob'] if cfg['use_rsi_filter'] else True
    rsi_short_ok = RSI > cfg['rsi_os'] if cfg['use_rsi_filter'] else True

    if cfg['use_ema_filter']:
        ema_long_ok = EMA_F > EMA_S and price > EMA_F
        ema_short_ok = EMA_F < EMA_S and price < EMA_F
        ema_trend = 'UP' if EMA_F > EMA_S else 'DOWN'
    else:
        ema_long_ok = ema_short_ok = True
        ema_trend = 'DISABLED'

    vol_long_ok = vol_short_ok = (VOL_RATIO >= cfg['vol_ratio_min']) if cfg['use_vol_filter'] else True
    macd_long_ok = (MACD > MACD_SIGNAL) if cfg['use_macd_filter'] else True
    macd_short_ok = (MACD < MACD_SIGNAL) if cfg['use_macd_filter'] else True

    if cfg['use_bb_filter']:
        bb_expanding = BB_WIDTH > BB_WIDTH_MA
        bb_long_ok = bb_expanding and (price <= BB_LOWER * 1.01)
        bb_short_ok = bb_expanding and (price >= BB_UPPER * 0.99)
    else:
        bb_long_ok = bb_short_ok = True

    obv_long_ok = (OBV > OBV_EMA) if cfg['use_obv_filter'] else True
    obv_short_ok = (OBV < OBV_EMA) if cfg['use_obv_filter'] else True
    roc_long_ok = (ROC > cfg['roc_long_min_allowed']) if cfg['use_roc_filter'] else True
    roc_short_ok = (ROC < cfg['roc_short_max_allowed']) if cfg['use_roc_filter'] else True

    if cfg['use_atr_trend_filter']:
        atr_long_ok = atr_short_ok = pd.notna(ATR_MA) and ATR > ATR_MA
    else:
        atr_long_ok = atr_short_ok = True

    def calc_strength(direction):
        score = 0
        if direction == 'LONG':
            if W < -90: score += 1
            if SK < 10: score += 1
            if RSI < 30: score += 1
        else:
            if W > -10: score += 1
            if SK > 90: score += 1
            if RSI > 70: score += 1
        return ['Normal', 'Güçlü', 'Çok Güçlü'][min(score, 2)]

    base = {
        'price': price,
        'atr': ATR,
        'atr_pct': atr_pct * 100,
        'willr': W,
        'stoch_k': SK,
        'stoch_d': SD,
        'rsi': RSI,
        'ema_trend': ema_trend,
        'vol_ratio': VOL_RATIO,
    }

    if wr_long and st_long and rsi_long_ok and ema_long_ok and vol_long_ok and macd_long_ok and bb_long_ok and obv_long_ok and roc_long_ok and atr_long_ok:
        return {
            **base,
            'direction': 'LONG',
            'stop': price - cfg['atr_mult_initial_stop'] * ATR,
            'take_profit': price + cfg['atr_mult_take_profit'] * ATR,
            'trail_active': False,
            'strength': calc_strength('LONG')
        }

    if wr_short and st_short and rsi_short_ok and ema_short_ok and vol_short_ok and macd_short_ok and bb_short_ok and obv_short_ok and roc_short_ok and atr_short_ok:
        return {
            **base,
            'direction': 'SHORT',
            'stop': price + cfg['atr_mult_initial_stop'] * ATR,
            'take_profit': price - cfg['atr_mult_take_profit'] * ATR,
            'trail_active': False,
            'strength': calc_strength('SHORT')
        }

    return {'direction': None}

def signal_allowed(sig):
    if sig.get('direction') is None:
        return False
    min_str = STRENGTH_ORDER.get(Config.CONFIG['min_strength'], 1)
    sig_str = STRENGTH_ORDER.get(sig.get('strength', 'Normal'), 1)
    return sig_str >= min_str
