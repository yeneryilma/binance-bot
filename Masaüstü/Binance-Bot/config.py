import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-me")
    API_KEY = os.getenv("BINANCE_API_KEY", "")
    API_SECRET = os.getenv("BINANCE_API_SECRET", "")
    TRADING_MODE = os.getenv("TRADING_MODE", "paper")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5000"))

    CONFIG = {
        'api_key': API_KEY,
        'api_secret': API_SECRET,
        'testnet': True,
        'interval': '15m',
        'interval_confirm': '1h',
        'min_candles': 300,
        'portfolio_usd': 500.0,
        'leverage': 5,
        'max_long': 15,
        'max_short': 15,
        'min_trade_usd': 5.0,

        'willr_window': 14,
        'willr_ob': -15,
        'willr_os': -85,

        'stoch_k': 14,
        'stoch_d': 3,
        'stoch_ob': 85,
        'stoch_os': 15,

        'rsi_span': 14,
        'rsi_ob': 65,
        'rsi_os': 35,

        'atr_span': 14,
        'atr_mult_initial_stop': 2.0,
        'trail_activation_mult': 1.1,
        'atr_mult_trail': 1.1,
        'atr_mult_take_profit': 10.0,

        'ema_fast': 50,
        'ema_slow': 200,
        'ema_htf_period':28,
        

        'vol_ma_period': 20,
        'vol_ratio_min': 1.2,

        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,

        'bb_period': 20,
        'bb_std': 2.0,

        'obv_ema_span': 20,

        'roc_period': 10,
        'roc_long_min_allowed': -5.0,
        'roc_short_max_allowed': 5.0,

        'atr_ma_period': 20,

        'use_rsi_filter': True,
        'use_ema_filter': False,
        'use_vol_filter': True,
        'use_htf_filter': False,
        'use_macd_filter': False,
        'use_bb_filter': False,
        'use_obv_filter': False,
        'use_roc_filter': False,
        'use_atr_trend_filter': False,
        'use_two_candle_confirm': False,
        'enable_reverse_exit': True,
        'enable_reverse_entry': True,

        'min_atr_pct': 0.003,
        'min_strength': 'Güçlü',
        'scan_interval_sec': 180,
        'request_delay': 0.2,
        'log_file': 'bot.log',
        'csv_file': 'closed_trades.csv',
        'trading_mode': TRADING_MODE,

        'symbols': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT', 'ADAUSDT']
    }

STRENGTH_ORDER = {'Normal': 1, 'Güçlü': 2, 'Çok Güçlü': 3}
