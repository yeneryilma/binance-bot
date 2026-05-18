import threading
from config import Config

state_lock = threading.Lock()

BOT = {
    'running': False,
    'pause_new_positions': False,
    'scanning': False,
    'scan_counter': 0,
    'portfolio_start': Config.CONFIG['portfolio_usd'],
    'realized_pnl': 0.0,
    'active_positions': {},
    'closed_trades': [],
    'logs': [],
}
