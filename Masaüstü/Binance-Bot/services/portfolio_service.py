from datetime import datetime
from core.state import BOT, state_lock
from config import Config
from services.logger_service import fmt
from services.persistence_service import save_trade_csv


def calc_position_size():
    with state_lock:
        pf = BOT['portfolio_start'] + BOT['realized_pnl']
    divisor = max(1, Config.CONFIG['max_long'] + Config.CONFIG['max_short'])
    return max(pf / divisor, Config.CONFIG['min_trade_usd'])


def calc_pnl(pos, exit_price):
    entry   = pos['entry']
    nominal = pos['size_usd'] * Config.CONFIG['leverage']
    if pos['direction'] == 'LONG':
        pnl_pct = (exit_price - entry) / entry * 100
        gross   = (exit_price - entry) / entry * nominal
    else:
        pnl_pct = (entry - exit_price) / entry * 100
        gross   = (entry - exit_price) / entry * nominal
    fee = nominal * 0.0008
    net = gross - fee
    return gross, net, pnl_pct


def update_trailing_stop(pos, current_price):
    cfg        = Config.CONFIG
    entry      = pos['entry']
    atr        = pos['atr']
    activation = cfg['trail_activation_mult'] * atr
    trail_dist = cfg['atr_mult_trail'] * atr

    if pos['direction'] == 'LONG':
        pos['highest'] = max(pos.get('highest', current_price), current_price)
        if not pos['trail_active'] and current_price >= entry + activation:
            pos['trail_active'] = True
        if pos['trail_active']:
            pos['stop'] = max(pos['stop'], current_price - trail_dist)
    else:
        pos['lowest'] = min(pos.get('lowest', current_price), current_price)
        if not pos['trail_active'] and current_price <= entry - activation:
            pos['trail_active'] = True
        if pos['trail_active']:
            pos['stop'] = min(pos['stop'], current_price + trail_dist)
    return pos


def build_state():
    with state_lock:
        positions  = dict(BOT['active_positions'])
        trades     = list(BOT['closed_trades'])
        logs       = list(BOT['logs'])
        realized   = BOT['realized_pnl']
        pf_start   = BOT['portfolio_start']
        running    = BOT['running']
        scanning   = BOT['scanning']
        scan_cnt   = BOT['scan_counter']
        pause      = BOT['pause_new_positions']

    unrealized = 0.0
    pos_list   = []
    for sym, p in positions.items():
        current             = p.get('current', p['entry'])
        _, net_pnl, pnl_pct = calc_pnl(p, current)
        unrealized         += net_pnl
        if p['direction'] == 'LONG':
            stop_dist = (current - p['stop']) / current * 100
        else:
            stop_dist = (p['stop'] - current) / current * 100
        age_min = int(
            (datetime.now() - datetime.fromisoformat(p['open_time'])).total_seconds() / 60
        )
        pos_list.append({
            'symbol'      : sym,
            'direction'   : p['direction'],
            'entry'       : fmt(p['entry']),
            'current'     : fmt(current),
            'stop'        : fmt(p['stop']),
            'size_usd'    : round(p['size_usd'], 2),
            'nominal'     : round(p['nominal'], 2),
            'net_pnl'     : round(net_pnl, 4),
            'pnl_pct'     : round(pnl_pct, 4),
            'lev_pct'     : round(pnl_pct * Config.CONFIG['leverage'], 2),
            'stop_dist'   : round(stop_dist, 2),
            'trail_active': p['trail_active'],
            'strength'    : p.get('strength', '—'),
            'htf_trend'   : p.get('htf_trend', '—'),
            'age_min'     : age_min,
        })

    portfolio_now   = pf_start + realized
    portfolio_total = portfolio_now + unrealized
    total_ret       = ((portfolio_total - pf_start) / pf_start * 100) if pf_start else 0

    total    = len(trades)
    wins     = sum(1 for t in trades if t['net_pnl'] > 0)
    win_rate = (wins / total * 100) if total else 0

    trade_list = []
    for t in reversed(trades):
        trade_list.append({
            'symbol'      : t['symbol'],
            'direction'   : t['direction'],
            'entry'       : fmt(t['entry']),
            'exit'        : fmt(t['exit']),
            'net_pnl'     : round(t['net_pnl'], 4),
            'pnl_pct'     : round(t['pnl_pct'], 4),
            'lev_pct'     : round(t['pnl_pct'] * Config.CONFIG['leverage'], 2),
            'duration_min': t['duration_min'],
            'reason'      : t['reason'],
            'trail_active': t['trail_active'],
            'strength'    : t.get('strength', '—'),
            'close_time'  : t['close_time'][:19].replace('T', ' '),
        })

    return {
        'running'        : running,
        'scanning'       : scanning,
        'scan_counter'   : scan_cnt,
        'pause_new'      : pause,
        'portfolio_start': round(pf_start, 2),
        'realized_pnl'   : round(realized, 4),
        'unrealized_pnl' : round(unrealized, 4),
        'portfolio_now'  : round(portfolio_now, 2),
        'portfolio_total': round(portfolio_total, 2),
        'total_ret_pct'  : round(total_ret, 2),
        'win_rate'       : round(win_rate, 1),
        'total_trades'   : total,
        'wins'           : wins,
        'losses'         : total - wins,
        'active_count'   : len(pos_list),
        'positions'      : pos_list,
        'closed_trades'  : trade_list,
        'logs'           : logs[-50:],
        'config'         : dict(Config.CONFIG),
    }


def open_position(symbol, sig, htf_trend, size_usd=None, fill_price=None, fill_qty=0.0):
    with state_lock:
        # ── AYNI SEMBOL KONTROLÜ ──────────────────────────────────
        if symbol in BOT['active_positions']:
            from services.logger_service import bot_log
            bot_log(f"[{symbol}] ⚠️ Zaten açık pozisyon var — yeni pozisyon engellendi")
            return False
        # ─────────────────────────────────────────────────────────

        longs  = sum(1 for p in BOT['active_positions'].values() if p['direction'] == 'LONG')
        shorts = sum(1 for p in BOT['active_positions'].values() if p['direction'] == 'SHORT')
        if sig['direction'] == 'LONG' and longs >= Config.CONFIG['max_long']:
            return False
        if sig['direction'] == 'SHORT' and shorts >= Config.CONFIG['max_short']:
            return False

        if size_usd is None:
            size_usd = calc_position_size()

        # fill_price > 0 kontrolü — 0.0 falsy olduğu için ayrı kontrol
        if fill_price is not None and fill_price > 0:
            entry_price = fill_price
        else:
            entry_price = sig['price']

        atr = sig['atr']
        if sig['direction'] == 'LONG':
            stop        = entry_price - Config.CONFIG['atr_mult_initial_stop'] * atr
            take_profit = entry_price + Config.CONFIG['atr_mult_take_profit'] * atr
        else:
            stop        = entry_price + Config.CONFIG['atr_mult_initial_stop'] * atr
            take_profit = entry_price - Config.CONFIG['atr_mult_take_profit'] * atr

        BOT['active_positions'][symbol] = {
            'symbol'      : symbol,
            'direction'   : sig['direction'],
            'entry'       : entry_price,
            'current'     : entry_price,
            'stop'        : stop,
            'take_profit' : take_profit,
            'trail_active': False,
            'atr'         : atr,
            'size_usd'    : size_usd,
            'nominal'     : size_usd * Config.CONFIG['leverage'],
            'qty'         : fill_qty,
            'open_time'   : datetime.now().isoformat(),
            'willr_entry' : sig['willr'],
            'stoch_entry' : sig['stoch_k'],
            'rsi_entry'   : sig['rsi'],
            'strength'    : sig['strength'],
            'ema_trend'   : sig['ema_trend'],
            'vol_ratio'   : sig['vol_ratio'],
            'htf_trend'   : htf_trend,
            'highest'     : entry_price,
            'lowest'      : entry_price,
            'net_pnl'     : 0.0,
            'pnl_pct'     : 0.0,
        }
    return True


def close_position(symbol, exit_price, reason):
    with state_lock:
        if symbol not in BOT['active_positions']:
            return None
        pos                  = BOT['active_positions'].pop(symbol)
        gross_pnl, net_pnl, pnl_pct = calc_pnl(pos, exit_price)
        BOT['realized_pnl'] += net_pnl
        duration_min = max(0, int(
            (datetime.now() - datetime.fromisoformat(pos['open_time'])).total_seconds() / 60
        ))
        trade = {
            'symbol'      : symbol,
            'direction'   : pos['direction'],
            'entry'       : pos['entry'],
            'exit'        : exit_price,
            'size_usd'    : pos['size_usd'],
            'nominal'     : pos['nominal'],
            'gross_pnl'   : gross_pnl,
            'net_pnl'     : net_pnl,
            'pnl_pct'     : pnl_pct,
            'duration_min': duration_min,
            'reason'      : reason,
            'trail_active': pos['trail_active'],
            'highest'     : pos.get('highest', pos['entry']),
            'lowest'      : pos.get('lowest',  pos['entry']),
            'willr_entry' : pos['willr_entry'],
            'stoch_entry' : pos['stoch_entry'],
            'rsi_entry'   : pos['rsi_entry'],
            'ema_trend'   : pos.get('ema_trend', 'N/A'),
            'vol_ratio'   : pos.get('vol_ratio', 0.0),
            'htf_trend'   : pos.get('htf_trend', 'N/A'),
            'strength'    : pos.get('strength', 'N/A'),
            'close_time'  : datetime.now().isoformat(),
        }
        BOT['closed_trades'].append(trade)
    save_trade_csv(trade)
    return trade
