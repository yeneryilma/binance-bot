import time
from config import Config
from services.logger_service import bot_log, fmt


def execute_open(symbol: str, signal: dict, size_usd: float):
    mode = Config.CONFIG['trading_mode']

    # ── PAPER ──────────────────────────────────────────────────────
    if mode == 'paper':
        from services.binance_service import fetch_price
        current = fetch_price(symbol)
        entry   = current if current else signal['price']
        return {
            'mode'     : 'paper',
            'status'   : 'filled',
            'symbol'   : symbol,
            'direction': signal['direction'],
            'price'    : entry,
            'qty'      : 0.0,
            'order_id' : f"paper-open-{symbol}-{int(time.time())}",
        }

    # ── TESTNET / LIVE ─────────────────────────────────────────────
    from services import binance_service
    try:
        leverage = Config.CONFIG['leverage']
        bot_log(f"[{symbol}] Kaldıraç ayarlanıyor: {leverage}x")
        binance_service.set_leverage(symbol, leverage)
        time.sleep(0.15)

        # Güncel fiyatı al — sinyal fiyatı değil
        current_price = binance_service.fetch_price(symbol)
        if not current_price:
            bot_log(f"[{symbol}] Güncel fiyat alınamadı")
            return None

        nominal  = size_usd * leverage
        raw_qty  = nominal / current_price
        real_qty = binance_service.round_qty(symbol, raw_qty)
        min_qty  = binance_service.get_min_qty(symbol)

        if real_qty < min_qty:
            bot_log(f"[{symbol}] Miktar çok küçük: {real_qty} < min {min_qty}")
            return None

        side = 'BUY' if signal['direction'] == 'LONG' else 'SELL'
        bot_log(
            f"[{symbol}] {mode.upper()} Emir → {side} {real_qty} "
            f"(Sinyal:{fmt(signal['price'])} Güncel:{fmt(current_price)})"
        )

        order = binance_service.create_market_order(symbol, side, real_qty)

        if not order:
            bot_log(f"[{symbol}] Emir başarısız")
            return None

        try:
            avg_price = float(order.get('avgPrice', 0) or 0)
        except (TypeError, ValueError):
            avg_price = 0.0

        # avgPrice gelmezse güncel fiyatı kullan — eski sinyal fiyatını değil
        if avg_price <= 0:
            avg_price = current_price

        bot_log(
            f"[{symbol}] ✅ {mode.upper()} AÇILDI | {side} | "
            f"Miktar:{real_qty} | Dolum:{fmt(avg_price)}"
        )

        return {
            'mode'     : mode,
            'status'   : 'filled',
            'symbol'   : symbol,
            'direction': signal['direction'],
            'price'    : avg_price,
            'qty'      : real_qty,
            'order_id' : str(order.get('orderId', '')),
        }

    except Exception as e:
        bot_log(f"[{symbol}] execute_open hata: {e}")
        return None


def execute_close(symbol: str, position: dict, exit_price: float):
    mode = Config.CONFIG['trading_mode']

    # ── PAPER ──────────────────────────────────────────────────────
    if mode == 'paper':
        from services.binance_service import fetch_price
        current = fetch_price(symbol)
        fill    = current if current else exit_price
        return {
            'mode'     : 'paper',
            'status'   : 'filled',
            'symbol'   : symbol,
            'price'    : fill,
            'qty'      : position.get('qty', 0.0),
            'order_id' : f"paper-close-{symbol}-{int(time.time())}",
        }

    # ── TESTNET / LIVE ─────────────────────────────────────────────
    from services import binance_service
    try:
        qty = position.get('qty', 0.0)
        if qty <= 0:
            bot_log(f"[{symbol}] Kapatma miktarı sıfır")
            return None

        side = 'SELL' if position['direction'] == 'LONG' else 'BUY'
        bot_log(f"[{symbol}] {mode.upper()} Kapatma → {side} {qty}")

        order = binance_service.create_market_order(symbol, side, qty, reduce_only=True)

        if not order:
            bot_log(f"[{symbol}] Kapatma emri başarısız")
            return None

        try:
            avg_price = float(order.get('avgPrice', 0) or 0)
        except (TypeError, ValueError):
            avg_price = 0.0

        if avg_price <= 0:
            current = binance_service.fetch_price(symbol)
            avg_price = current if current else exit_price

        bot_log(
            f"[{symbol}] ✅ {mode.upper()} KAPATILDI | {side} | "
            f"Miktar:{qty} | Dolum:{fmt(avg_price)}"
        )

        return {
            'mode'     : mode,
            'status'   : 'filled',
            'symbol'   : symbol,
            'price'    : avg_price,
            'qty'      : qty,
            'order_id' : str(order.get('orderId', '')),
        }

    except Exception as e:
        bot_log(f"[{symbol}] execute_close hata: {e}")
        return None
