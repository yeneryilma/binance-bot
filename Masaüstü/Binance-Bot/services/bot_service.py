import time
import threading
from core.state import BOT, state_lock
from config import Config
from services.logger_service import bot_log, fmt
from services.binance_service import fetch_klines, fetch_price, get_client, reset_client
from services.indicator_service import add_indicators, get_htf_trend
from services.signal_service import get_signal, signal_allowed
from services.execution_service import execute_open, execute_close
from services.portfolio_service import (
    open_position, close_position, update_trailing_stop,
    calc_position_size
)
from services.persistence_service import init_csv

bot_thread   = None
push_thread  = None
stop_thread  = None
socketio_ref = None


# ─────────────────────────────────────────────────────────────────────
# STOP MONİTÖR — her 5 saniyede bir çalışır
# Taramalar arası stop/TP kaçmasını önler
# ─────────────────────────────────────────────────────────────────────
def stop_monitor_loop():
    while True:
        try:
            with state_lock:
                if not BOT['running']:
                    break
                symbols = list(BOT['active_positions'].keys())

            for symbol in symbols:
                try:
                    current = fetch_price(symbol)
                    if not current:
                        continue

                    with state_lock:
                        if symbol not in BOT['active_positions']:
                            continue
                        pos = BOT['active_positions'][symbol]
                        pos = update_trailing_stop(pos, current)
                        pos['current'] = current
                        pos['highest'] = max(pos.get('highest', current), current)
                        pos['lowest']  = min(pos.get('lowest',  current), current)
                        BOT['active_positions'][symbol] = pos
                        direction = pos['direction']
                        stop      = pos['stop']
                        tp        = pos.get('take_profit')
                        trail     = pos['trail_active']

                    hit    = False
                    reason = ''

                    if direction == 'LONG':
                        if current <= stop:
                            hit    = True
                            reason = 'Trailing Stop' if trail else 'İlk Stop'
                        elif tp and current >= tp:
                            hit    = True
                            reason = 'Take Profit'
                    else:
                        if current >= stop:
                            hit    = True
                            reason = 'Trailing Stop' if trail else 'İlk Stop'
                        elif tp and current <= tp:
                            hit    = True
                            reason = 'Take Profit'

                    if hit:
                        with state_lock:
                            if symbol not in BOT['active_positions']:
                                continue
                            pos_snap = BOT['active_positions'].get(symbol)
                        if pos_snap:
                            result = execute_close(symbol, pos_snap, current)
                            fill   = result['price'] if result else current
                            close_position(symbol, fill, reason)
                            bot_log(
                                f"[{symbol}] 🔴 STOP MONİTÖR → "
                                f"{reason} @ {fmt(fill)}"
                            )

                except Exception as e:
                    bot_log(f"Stop monitör hata [{symbol}]: {e}")

                time.sleep(0.1)   # semboller arası 100ms

        except Exception as e:
            bot_log(f"Stop monitör genel hata: {e}")

        time.sleep(5)   # tüm semboller bittikten sonra 5sn bekle


# ─────────────────────────────────────────────────────────────────────
# SEMBOL TARAMA
# ─────────────────────────────────────────────────────────────────────
def scan_symbol(symbol: str):
    with state_lock:
        in_position = symbol in BOT['active_positions']

    # ── POZİSYON VAR ─────────────────────────────────────────────────
    if in_position:
        current = fetch_price(symbol)
        if current is None:
            return {'symbol': symbol, 'result': 'skip'}

        reverse_sig = None
        df = fetch_klines(symbol)
        if df is not None:
            df = add_indicators(df)
            df.dropna(inplace=True)
            if len(df) >= 6:
                reverse_sig = get_signal(df)

        with state_lock:
            if symbol not in BOT['active_positions']:
                return {'symbol': symbol, 'result': 'skip'}
            pos = BOT['active_positions'][symbol]
            pos['highest'] = max(pos.get('highest', current), current)
            pos['lowest']  = min(pos.get('lowest',  current), current)
            pos = update_trailing_stop(pos, current)
            pos['current'] = current
            BOT['active_positions'][symbol] = pos
            direction = pos['direction']
            stop      = pos['stop']
            tp        = pos.get('take_profit')

        def do_close(reason):
            with state_lock:
                if symbol not in BOT['active_positions']:
                    return
                pos_snap = BOT['active_positions'].get(symbol)
            if not pos_snap:
                return
            result = execute_close(symbol, pos_snap, current)
            fill   = result['price'] if result else current
            close_position(symbol, fill, reason)

        if direction == 'LONG':
            if current <= stop:
                do_close('Trailing Stop' if pos['trail_active'] else 'İlk Stop')
                return {'symbol': symbol, 'result': 'closed'}
            if tp and current >= tp:
                do_close('Take Profit')
                return {'symbol': symbol, 'result': 'closed'}
        else:
            if current >= stop:
                do_close('Trailing Stop' if pos['trail_active'] else 'İlk Stop')
                return {'symbol': symbol, 'result': 'closed'}
            if tp and current <= tp:
                do_close('Take Profit')
                return {'symbol': symbol, 'result': 'closed'}

        # Ters sinyal çıkışı
        if (reverse_sig and reverse_sig.get('direction')
                and reverse_sig['direction'] != direction
                and signal_allowed(reverse_sig)
                and Config.CONFIG['enable_reverse_exit']):

            with state_lock:
                if symbol not in BOT['active_positions']:
                    return {'symbol': symbol, 'result': 'skip'}
                pos_snap = BOT['active_positions'].get(symbol)
            if pos_snap:
                result = execute_close(symbol, pos_snap, current)
                fill   = result['price'] if result else current
                close_position(symbol, fill, 'Ters Sinyal Çıkışı')

            if Config.CONFIG['enable_reverse_entry']:
                htf = 'DISABLED'
                if Config.CONFIG['use_htf_filter']:
                    htf = get_htf_trend(symbol, fetch_klines)
                size_usd    = calc_position_size()
                exec_result = execute_open(symbol, reverse_sig, size_usd)
                if exec_result:
                    with state_lock:
                        already_open = symbol in BOT['active_positions']
                    if not already_open:
                        open_position(
                            symbol, reverse_sig, htf,
                            size_usd   = size_usd,
                            fill_price = exec_result['price'],
                            fill_qty   = exec_result['qty'],
                        )
            return {'symbol': symbol, 'result': 'reversed'}

        return {'symbol': symbol, 'result': 'monitoring'}

    # ── POZİSYON YOK ─────────────────────────────────────────────────
    with state_lock:
        pause = BOT['pause_new_positions']
    if pause:
        return {'symbol': symbol, 'result': 'paused'}

    df = fetch_klines(symbol)
    if df is None:
        return {'symbol': symbol, 'result': 'skip'}

    df = add_indicators(df)
    df.dropna(inplace=True)
    if len(df) < 6:
        return {'symbol': symbol, 'result': 'skip'}

    sig = get_signal(df)

    if not signal_allowed(sig):
        return {'symbol': symbol, 'result': 'no_signal'}

    # 1. ÖNCE HTF KONTROLÜ — tüm API çağrıları burada biter
    htf_trend = 'DISABLED'
    if Config.CONFIG['use_htf_filter']:
        htf_trend = get_htf_trend(symbol, fetch_klines)
        if htf_trend == 'FLAT':
            return {'symbol': symbol, 'result': 'htf_flat'}
        if sig['direction'] == 'LONG' and htf_trend != 'UP':
            return {'symbol': symbol, 'result': 'htf_mismatch'}
        if sig['direction'] == 'SHORT' and htf_trend != 'DOWN':
            return {'symbol': symbol, 'result': 'htf_mismatch'}

    # 2. SONRA FİYAT KONTROLÜ — execute'dan hemen önce, taze fiyat
    current_price = fetch_price(symbol)
    if current_price and current_price > 0:
        price_diff_pct = abs(current_price - sig['price']) / sig['price'] * 100
        if price_diff_pct > 1.0:
            bot_log(
                f"[{symbol}] ⚠️ Fiyat farkı: "
                f"Sinyal={fmt(sig['price'])} "
                f"Güncel={fmt(current_price)} "
                f"Fark=%{price_diff_pct:.2f}"
            )
        if price_diff_pct > 3.0:
            bot_log(
                f"[{symbol}] ❌ Fiyat farkı çok büyük "
                f"(%{price_diff_pct:.2f}) — sinyal iptal"
            )
            return {'symbol': symbol, 'result': 'price_stale'}
        sig['price'] = current_price

    # 3. EXECUTE — fiyat taze, hemen aç
    size_usd    = calc_position_size()
    exec_result = execute_open(symbol, sig, size_usd)

    if exec_result is None:
        bot_log(f"[{symbol}] Emir başarısız — pozisyon açılmadı")
        return {'symbol': symbol, 'result': 'exec_fail'}

    # Çift pozisyon kontrolü
    with state_lock:
        if symbol in BOT['active_positions']:
            bot_log(f"[{symbol}] ⚠️ API süresinde pozisyon açıldı — tekrar engellendi")
            return {'symbol': symbol, 'result': 'duplicate_blocked'}

    ok = open_position(
        symbol, sig, htf_trend,
        size_usd   = size_usd,
        fill_price = exec_result['price'],
        fill_qty   = exec_result['qty'],
    )

    if ok:
        bot_log(
            f"POZİSYON AÇILDI | {symbol} | {sig['direction']} | "
            f"Fiyat:{fmt(exec_result['price'])} | "
            f"Stop:{fmt(sig['stop'])} | "
            f"TP:{fmt(sig['take_profit'])} | "
            f"Mod:{Config.CONFIG['trading_mode'].upper()}"
        )
        return {'symbol': symbol, 'result': sig['direction']}

    return {'symbol': symbol, 'result': 'limit'}


# ─────────────────────────────────────────────────────────────────────
# TARAMA DÖNGÜSÜ
# ─────────────────────────────────────────────────────────────────────
def run_scan():
    with state_lock:
        if BOT['scanning']:
            return
        BOT['scanning']     = True
        BOT['scan_counter'] += 1
        scan_num = BOT['scan_counter']

    bot_log(f"Tarama #{scan_num} başladı")
    results = {'long': 0, 'short': 0, 'closed': 0}

    for symbol in Config.CONFIG['symbols']:
        with state_lock:
            if not BOT['running']:
                break
        try:
            r = scan_symbol(symbol)
            if r['result'] == 'LONG':
                results['long'] += 1
            elif r['result'] == 'SHORT':
                results['short'] += 1
            elif r['result'] in ('closed', 'reversed'):
                results['closed'] += 1
        except Exception as e:
            bot_log(f"Hata [{symbol}]: {e}")
        time.sleep(Config.CONFIG['request_delay'])

    with state_lock:
        BOT['scanning'] = False

    bot_log(
        f"Tarama #{scan_num} tamamlandı → "
        f"LONG:{results['long']} SHORT:{results['short']} "
        f"Kapandı:{results['closed']}"
    )
    if socketio_ref:
        socketio_ref.emit('scan_complete', {
            'scan_num': scan_num,
            'results' : results
        })


def bot_loop():
    while True:
        with state_lock:
            if not BOT['running']:
                break
        started = time.time()
        run_scan()
        elapsed  = time.time() - started
        wait_sec = max(1, int(Config.CONFIG['scan_interval_sec'] - elapsed))
        for _ in range(wait_sec):
            with state_lock:
                if not BOT['running']:
                    return
            time.sleep(1)


def push_loop(build_state_func):
    while True:
        try:
            if socketio_ref:
                socketio_ref.emit('state_update', build_state_func())
        except Exception:
            pass
        time.sleep(2)


# ─────────────────────────────────────────────────────────────────────
# BAŞLAT / DURDUR
# ─────────────────────────────────────────────────────────────────────
def start_bot(socketio, build_state_func):
    global bot_thread, push_thread, stop_thread, socketio_ref
    socketio_ref = socketio

    with state_lock:
        if BOT['running']:
            return False, 'Bot zaten çalışıyor'
        BOT['running'] = True

    try:
        reset_client()
        get_client()
        init_csv()
    except Exception as e:
        with state_lock:
            BOT['running'] = False
        return False, f'Bağlantı hatası: {e}'

    # Ana tarama thread'i
    bot_thread = threading.Thread(target=bot_loop, daemon=True)
    bot_thread.start()

    # Stop monitör thread'i
    if stop_thread is None or not stop_thread.is_alive():
        stop_thread = threading.Thread(target=stop_monitor_loop, daemon=True)
        stop_thread.start()

    # UI güncelleme thread'i
    if push_thread is None or not push_thread.is_alive():
        push_thread = threading.Thread(
            target=push_loop, args=(build_state_func,), daemon=True
        )
        push_thread.start()

    mode = Config.CONFIG['trading_mode'].upper()
    bot_log(f"BOT BAŞLATILDI — Mod: {mode}")
    return True, f'Bot başlatıldı ({mode})'


def stop_bot():
    with state_lock:
        BOT['running'] = False
    bot_log("BOT DURDURULDU")
    return True, 'Bot durduruldu'
