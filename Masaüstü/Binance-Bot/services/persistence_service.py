import os
import csv
from config import Config
from services.logger_service import fmt
from core.state import BOT

def init_csv():
    if not os.path.exists(Config.CONFIG['csv_file']):
        with open(Config.CONFIG['csv_file'], 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow([
                'Tarih','Sembol','Yön','Giriş','Çıkış',
                'Marjin($)','Nominal($)','Kaldıraç',
                'Brüt P&L($)','Net P&L($)','P&L(%)','Kld P&L(%)',
                'Süre(dk)','Çıkış Nedeni','Trailing','En Yüksek','En Düşük',
                'WR','Stoch','RSI','EMA','HacimOranı','HTF','Güç','Portföy($)'
            ])

def save_trade_csv(trade):
    portfolio_now = BOT['portfolio_start'] + BOT['realized_pnl']
    with open(Config.CONFIG['csv_file'], 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([
            trade['close_time'][:19].replace('T', ' '),
            trade['symbol'], trade['direction'],
            fmt(trade['entry']), fmt(trade['exit']),
            f"{trade['size_usd']:.2f}", f"{trade['nominal']:.2f}",
            Config.CONFIG['leverage'],
            f"{trade['gross_pnl']:.4f}", f"{trade['net_pnl']:.4f}",
            f"{trade['pnl_pct']:.4f}", f"{trade['pnl_pct'] * Config.CONFIG['leverage']:.4f}",
            trade['duration_min'], trade['reason'], trade['trail_active'],
            fmt(trade['highest']), fmt(trade['lowest']),
            f"{trade['willr_entry']:.2f}", f"{trade['stoch_entry']:.2f}",
            f"{trade['rsi_entry']:.2f}", trade['ema_trend'],
            f"{trade['vol_ratio']:.2f}", trade['htf_trend'],
            trade['strength'], f"{portfolio_now:.2f}",
        ])
