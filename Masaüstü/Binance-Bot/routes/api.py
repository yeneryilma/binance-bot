from flask import Blueprint, jsonify, request
from core.state import BOT, state_lock
from config import Config
from services.bot_service import start_bot, stop_bot, run_scan
from services.portfolio_service import build_state, close_position
from services.binance_service import fetch_price, reset_client
from services.logger_service import bot_log

def parse_bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, str):  return v.lower() in ('1','true','yes','on')
    return bool(v)

api_bp = Blueprint('api', __name__, url_prefix='/api')
socketio_holder = {'socketio': None}

def set_socketio(socketio):
    socketio_holder['socketio'] = socketio

@api_bp.get('/state')
def api_state():
    return jsonify(build_state())

@api_bp.post('/start')
def api_start():
    ok, msg = start_bot(socketio_holder['socketio'], build_state)
    return jsonify({'ok': ok, 'msg': msg})

@api_bp.post('/stop')
def api_stop():
    ok, msg = stop_bot()
    return jsonify({'ok': ok, 'msg': msg})

@api_bp.post('/stop_all')
def api_stop_all():
    with state_lock:
        BOT['running'] = False
        symbols = list(BOT['active_positions'].keys())

    closed = []
    for sym in symbols:
        price = fetch_price(sym)
        if price is None:
            with state_lock:
                p = BOT['active_positions'].get(sym)
            price = p['entry'] if p else 0
        close_position(sym, price, 'Manuel — Tümünü Kapat & Dur')
        closed.append(sym)

    bot_log(f"Bot durduruldu. {len(closed)} pozisyon kapatıldı.")
    return jsonify({'ok': True, 'msg': f'{len(closed)} pozisyon kapatıldı', 'closed': closed})

@api_bp.post('/close/<symbol>')
def api_close(symbol):
    with state_lock:
        exists = symbol in BOT['active_positions']
    if not exists:
        return jsonify({'ok': False, 'msg': 'Pozisyon bulunamadı'}), 404
    price = fetch_price(symbol)
    if price is None:
        with state_lock:
            p = BOT['active_positions'].get(symbol)
        price = p['entry'] if p else 0
    close_position(symbol, price, 'Manuel Kapama')
    return jsonify({'ok': True, 'msg': f'{symbol} kapatıldı'})

@api_bp.post('/toggle_pause')
def api_toggle_pause():
    with state_lock:
        BOT['pause_new_positions'] = not BOT['pause_new_positions']
        paused = BOT['pause_new_positions']
    return jsonify({'ok': True, 'paused': paused})

@api_bp.post('/scan')
def api_scan():
    import threading
    threading.Thread(target=run_scan, daemon=True).start()
    return jsonify({'ok': True, 'msg': 'Manuel tarama başlatıldı'})

# ── MOD DEĞİŞTİRME ────────────────────────────────
@api_bp.post('/set_mode')
def api_set_mode():
    data = request.json or {}
    mode = data.get('mode', 'paper')

    if mode not in ('paper', 'live'):
        return jsonify({'ok': False, 'msg': 'Geçersiz mod. paper veya live olmalı'})

    with state_lock:
        running = BOT['running']

    if running:
        return jsonify({
            'ok' : False,
            'msg': 'Bot çalışırken mod değiştirilemez. Önce botu durdurun.'
        })

    Config.CONFIG['trading_mode'] = mode
    reset_client()

    bot_log(f"MOD DEĞİŞTİRİLDİ → {mode.upper()}")
    return jsonify({
        'ok'  : True,
        'mode': mode,
        'msg' : f'Mod {mode.upper()} olarak ayarlandı'
    })

# ── CONFIG ────────────────────────────────────────
@api_bp.get('/config')
def api_get_config():
    return jsonify({'ok': True, 'config': dict(Config.CONFIG)})

@api_bp.post('/config')
def api_set_config():
    data = request.json or {}

    int_keys = [
        'leverage','max_long','max_short','willr_window','stoch_k','stoch_d',
        'rsi_span','atr_span','ema_fast','ema_slow','ema_confirm_fast','ema_confirm_slow',
        'vol_ma_period','scan_interval_sec','min_candles','macd_fast','macd_slow',
        'macd_signal','bb_period','obv_ema_span','roc_period','atr_ma_period','ema_htf_period',
    ]
    float_keys = [
        'portfolio_usd','min_trade_usd','willr_ob','willr_os','stoch_ob','stoch_os',
        'rsi_ob','rsi_os','vol_ratio_min','atr_mult_initial_stop','trail_activation_mult',
        'atr_mult_trail','atr_mult_take_profit','min_atr_pct','bb_std',
        'roc_long_min_allowed','roc_short_max_allowed',
    ]
    bool_keys = [
        'testnet','use_rsi_filter','use_ema_filter','use_vol_filter','use_htf_filter',
        'use_macd_filter','use_bb_filter','use_obv_filter','use_roc_filter',
        'use_atr_trend_filter','use_two_candle_confirm','enable_reverse_exit','enable_reverse_entry',
    ]
    str_keys = [
        'api_key','api_secret','interval','interval_confirm','min_strength','trading_mode',
    ]

    for k, v in data.items():
        if k not in Config.CONFIG:
            continue
        try:
            if k in int_keys:
                Config.CONFIG[k] = int(float(v))
            elif k in float_keys:
                Config.CONFIG[k] = float(v)
            elif k in bool_keys:
                Config.CONFIG[k] = parse_bool(v)
            elif k in str_keys:
                Config.CONFIG[k] = str(v)
            elif k == 'symbols' and isinstance(v, list):
                Config.CONFIG[k] = [str(x).upper() for x in v if str(x).strip()]
        except Exception:
            pass

    # API bilgileri değiştiyse client sıfırla
    reset_client()

    return jsonify({'ok': True, 'config': dict(Config.CONFIG)})
