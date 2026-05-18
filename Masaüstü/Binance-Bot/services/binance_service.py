import math
import time
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import Config
from services.logger_service import bot_log

client = None
_symbol_info_cache = {}

def reset_client():
    global client, _symbol_info_cache
    client = None
    _symbol_info_cache = {}

def get_client():
    global client
    if client is not None:
        return client

    mode        = Config.CONFIG['trading_mode']
    api_key     = Config.CONFIG['api_key']
    api_secret  = Config.CONFIG['api_secret']
    use_testnet = (mode == 'testnet') or Config.CONFIG.get('testnet', False)

    c = Client(api_key, api_secret, testnet=use_testnet)

    if use_testnet:
        c.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

    client = c
    return c

def fetch_klines(symbol: str, interval: str = None, limit: int = 500):
    c = get_client()
    try:
        iv  = interval or Config.CONFIG['interval']
        raw = c.futures_klines(symbol=symbol, interval=iv, limit=limit)
        df  = pd.DataFrame(raw, columns=[
            'open_time','Open','High','Low','Close','Volume',
            'close_time','quote_vol','trades',
            'taker_buy_base','taker_buy_quote','ignore'
        ])
        df = df[['open_time','Open','High','Low','Close','Volume']].copy()
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('open_time', inplace=True)
        for col in ['Open','High','Low','Close','Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < Config.CONFIG['min_candles']:
            return None
        return df
    except BinanceAPIException as e:
        bot_log(f"API hata [{symbol}]: {e}")
        return None
    except Exception as e:
        bot_log(f"Kline hata [{symbol}]: {e}")
        return None

def fetch_price(symbol: str):
    c = get_client()
    try:
        return float(c.futures_symbol_ticker(symbol=symbol)['price'])
    except Exception:
        return None

def get_symbol_info(symbol: str):
    global _symbol_info_cache
    if symbol in _symbol_info_cache:
        return _symbol_info_cache[symbol]
    try:
        c    = get_client()
        info = c.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == symbol:
                _symbol_info_cache[symbol] = s
                return s
    except Exception as e:
        bot_log(f"Symbol info hata [{symbol}]: {e}")
    return None

def get_step_size(symbol: str) -> float:
    info = get_symbol_info(symbol)
    if not info:
        return 0.001
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            return float(f['stepSize'])
    return 0.001

def get_min_qty(symbol: str) -> float:
    info = get_symbol_info(symbol)
    if not info:
        return 0.001
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            return float(f['minQty'])
    return 0.001

def round_qty(symbol: str, qty: float) -> float:
    step = get_step_size(symbol)
    if step <= 0:
        return round(qty, 3)
    precision = max(0, round(-math.log10(step)))
    factor    = 10 ** precision
    return math.floor(qty * factor) / factor

def set_leverage(symbol: str, leverage: int) -> bool:
    try:
        c = get_client()
        c.futures_change_leverage(symbol=symbol, leverage=leverage)
        return True
    except BinanceAPIException as e:
        bot_log(f"Kaldıraç hata [{symbol}]: {e}")
        return False
    except Exception as e:
        bot_log(f"Kaldıraç genel hata [{symbol}]: {e}")
        return False

def create_market_order(symbol: str, side: str, qty: float, reduce_only: bool = False):
    try:
        c      = get_client()
        params = {
            'symbol'  : symbol,
            'side'    : side,
            'type'    : 'MARKET',
            'quantity': qty,
        }
        if reduce_only:
            params['reduceOnly'] = True
        order = c.futures_create_order(**params)
        return order
    except BinanceAPIException as e:
        bot_log(f"Emir hata [{symbol}] {side} qty:{qty} → {e}")
        return None
    except Exception as e:
        bot_log(f"Emir genel hata [{symbol}]: {e}")
        return None

def get_open_positions():
    try:
        c         = get_client()
        positions = c.futures_position_information()
        return [p for p in positions if float(p['positionAmt']) != 0]
    except Exception as e:
        bot_log(f"Pozisyon listesi hata: {e}")
        return []
