from datetime import datetime
from core.state import BOT, state_lock
from config import Config

def bot_log(msg: str):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    with state_lock:
        BOT['logs'].append(line)
        BOT['logs'] = BOT['logs'][-300:]
    try:
        with open(Config.CONFIG['log_file'], 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def fmt(p: float) -> str:
    if p == 0:
        return "0"
    if abs(p) < 0.0001:
        return f"{p:.8f}"
    if abs(p) < 0.01:
        return f"{p:.6f}"
    if abs(p) < 1:
        return f"{p:.5f}"
    if abs(p) < 100:
        return f"{p:.4f}"
    return f"{p:.2f}"
