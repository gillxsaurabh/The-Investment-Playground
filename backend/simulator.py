import json
import os
import time
import random
import threading
from datetime import datetime, timedelta


class PaperTradingSimulator:
    """Paper trading engine that executes virtual trades and tracks P&L using live Kite prices."""

    SPREAD_FACTOR = 0.0005  # 0.05% impact cost
    MAX_HISTORY_SECONDS = 3600  # Keep 1 hour of price snapshots

    def __init__(self, kite, data_file='simulator_data.json', history_file='simulator_price_history.json'):
        self.kite = kite
        self.data_file = data_file
        self.history_file = history_file
        self._lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._load_data()
        self._load_price_history()

    def _load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r') as f:
                self._data = json.load(f)
            # Migrate any old-format positions to trailing stop format
            migrated = False
            for i, p in enumerate(self._data['active_positions']):
                if 'current_sl' not in p:
                    self._data['active_positions'][i] = self._migrate_position_to_trailing(p)
                    migrated = True
            if migrated:
                self._save_data()
        else:
            self._data = {
                "account_summary": {
                    "initial_capital": 100000.0,
                    "current_balance": 100000.0,
                    "total_pnl": 0.0
                },
                "active_positions": [],
                "trade_history": []
            }
            self._save_data()

    def _save_data(self):
        with open(self.data_file, 'w') as f:
            json.dump(self._data, f, indent=2, default=str)

    def _load_price_history(self):
        """Load price history from file, pruning entries older than 1 hour."""
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                self._price_history = json.load(f)
        else:
            self._price_history = []
        self._prune_history()

    def _save_price_history(self):
        with open(self.history_file, 'w') as f:
            json.dump(self._price_history, f, default=str)

    def _prune_history(self):
        """Remove snapshots older than MAX_HISTORY_SECONDS."""
        cutoff = (datetime.now() - timedelta(seconds=self.MAX_HISTORY_SECONDS)).strftime('%Y-%m-%d %H:%M:%S')
        self._price_history = [s for s in self._price_history if s['time'] >= cutoff]

    def record_price_snapshot(self):
        """Record current normalized % values for all active positions. Called by the monitor."""
        with self._lock:
            positions = self._data['active_positions']
            if not positions:
                return

            symbols = [p['symbol'] for p in positions]
            try:
                ltps = self._fetch_ltps(symbols)
            except Exception:
                return

        # Build snapshot outside data lock
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        values = {}
        for p in positions:
            ltp = ltps.get(p['symbol'])
            if ltp and p['entry_price']:
                values[p['symbol']] = {
                    'pct': round(((ltp - p['entry_price']) / p['entry_price']) * 100, 4),
                    'ltp': ltp,
                    'entry_price': p['entry_price'],
                    'stop_loss': p.get('current_sl', p.get('stop_loss', 0)),
                    'highest_price_seen': p.get('highest_price_seen', p['entry_price']),
                    'unrealized_pnl': round((ltp - p['entry_price']) * p['quantity'], 2),
                    'quantity': p['quantity'],
                }

        with self._history_lock:
            self._price_history.append({'time': now, 'values': values})
            self._prune_history()
            self._save_price_history()

    def get_price_history(self, minutes=60):
        """Return price history for the last N minutes."""
        with self._history_lock:
            cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
            return [s for s in self._price_history if s['time'] >= cutoff]

    def _fetch_ltp(self, symbol):
        """Fetch live LTP from Kite for a single symbol."""
        key = f'NSE:{symbol}'
        quote = self.kite.quote([key])
        return quote[key]['last_price']

    def _fetch_ltps(self, symbols):
        """Batch fetch LTPs for multiple symbols. Returns {symbol: ltp}."""
        if not symbols:
            return {}
        keys = [f'NSE:{s}' for s in symbols]
        quotes = self.kite.quote(keys)
        return {s: quotes[f'NSE:{s}']['last_price'] for s in symbols}

    def execute_order(self, symbol, quantity, atr_at_entry, trail_multiplier=1.5, instrument_token=None):
        """Execute a virtual buy order with spread simulation and trailing stop."""
        with self._lock:
            ltp = self._fetch_ltp(symbol)
            entry_price = round(ltp * (1 + self.SPREAD_FACTOR), 2)
            total_cost = entry_price * quantity

            if self._data['account_summary']['current_balance'] < total_cost:
                return {
                    'success': False,
                    'error': 'Insufficient Virtual Funds',
                    'required': total_cost,
                    'available': self._data['account_summary']['current_balance']
                }

            now = datetime.now()
            trade_id = f"SIM_{now.strftime('%d%m%y')}_{symbol}_{random.randint(1000, 9999)}"
            initial_sl = round(entry_price - (trail_multiplier * atr_at_entry), 2)

            position = {
                'trade_id': trade_id,
                'symbol': symbol,
                'instrument_token': instrument_token,
                'entry_price': entry_price,
                'quantity': quantity,
                'atr_at_entry': round(atr_at_entry, 2),
                'current_sl': initial_sl,
                'highest_price_seen': entry_price,
                'last_new_high_date': now.strftime('%Y-%m-%d'),
                'trail_multiplier': trail_multiplier,
                'stop_loss': initial_sl,  # backward compat alias
                'entry_time': now.strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'OPEN'
            }

            self._data['account_summary']['current_balance'] -= total_cost
            self._data['account_summary']['current_balance'] = round(
                self._data['account_summary']['current_balance'], 2
            )
            self._data['active_positions'].append(position)
            self._save_data()

            return {
                'success': True,
                'trade_id': trade_id,
                'symbol': symbol,
                'entry_price': entry_price,
                'quantity': quantity,
                'total_cost': total_cost,
                'current_sl': initial_sl,
                'trail_multiplier': trail_multiplier,
                'message': f'Virtual BUY executed: {quantity} x {symbol} @ {entry_price}'
            }

    def close_position(self, trade_id, exit_price=None, reason='Manual Close'):
        """Close a virtual position and move to history."""
        with self._lock:
            position = None
            idx = None
            for i, p in enumerate(self._data['active_positions']):
                if p['trade_id'] == trade_id:
                    position = p
                    idx = i
                    break

            if position is None:
                return {'success': False, 'error': f'Position {trade_id} not found'}

            if exit_price is None:
                ltp = self._fetch_ltp(position['symbol'])
                exit_price = round(ltp * (1 - self.SPREAD_FACTOR), 2)

            credit = exit_price * position['quantity']
            realized_pnl = round((exit_price - position['entry_price']) * position['quantity'], 2)

            self._data['account_summary']['current_balance'] += credit
            self._data['account_summary']['current_balance'] = round(
                self._data['account_summary']['current_balance'], 2
            )
            self._data['account_summary']['total_pnl'] += realized_pnl
            self._data['account_summary']['total_pnl'] = round(
                self._data['account_summary']['total_pnl'], 2
            )

            history_entry = {
                **position,
                'exit_price': exit_price,
                'exit_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'realized_pnl': realized_pnl,
                'reason': reason,
                'status': 'CLOSED'
            }

            self._data['active_positions'].pop(idx)
            self._data['trade_history'].insert(0, history_entry)
            self._save_data()

            return {
                'success': True,
                'trade_id': trade_id,
                'symbol': position['symbol'],
                'exit_price': exit_price,
                'realized_pnl': realized_pnl,
                'reason': reason,
                'message': f"Virtual SELL: {position['symbol']} @ {exit_price} | P&L: {realized_pnl}"
            }

    def get_positions_with_pnl(self):
        """Get all active positions enriched with live LTP and unrealized P&L."""
        with self._lock:
            positions = self._data['active_positions']
            if not positions:
                return {
                    'account_summary': self._data['account_summary'],
                    'positions': [],
                    'trade_history': self._data['trade_history']
                }

            symbols = [p['symbol'] for p in positions]
            try:
                ltps = self._fetch_ltps(symbols)
            except Exception:
                ltps = {}

            enriched = []
            total_unrealized = 0.0
            for p in positions:
                ltp = ltps.get(p['symbol'], p['entry_price'])
                unrealized_pnl = round((ltp - p['entry_price']) * p['quantity'], 2)
                total_unrealized += unrealized_pnl
                enriched.append({
                    **p,
                    'ltp': ltp,
                    'unrealized_pnl': unrealized_pnl
                })

            return {
                'account_summary': {
                    **self._data['account_summary'],
                    'unrealized_pnl': round(total_unrealized, 2)
                },
                'positions': enriched,
                'trade_history': self._data['trade_history']
            }

    def update_exit_levels(self, position, ltp):
        """
        Update trailing stop for a position based on current price.
        Returns (updated_position, exit_signal or None).
        exit_signal = {'should_exit': True, 'reason': str, 'exit_price': float}
        """
        today = datetime.now().date()

        # Step A: Update high-water mark
        if ltp > position.get('highest_price_seen', position['entry_price']):
            position['highest_price_seen'] = ltp
            position['last_new_high_date'] = today.strftime('%Y-%m-%d')

        # Step B: Ratchet the trailing stop loss UP (never down)
        atr = position.get('atr_at_entry', 0)
        multiplier = position.get('trail_multiplier', 1.5)
        if atr > 0:
            new_sl = round(position['highest_price_seen'] - (multiplier * atr), 2)
            current_sl = position.get('current_sl', position.get('stop_loss', 0))
            if new_sl > current_sl:
                position['current_sl'] = new_sl
                position['stop_loss'] = new_sl  # keep alias in sync

        # Step C: Check for stall (no new high in 7+ days)
        last_high_str = position.get('last_new_high_date')
        if last_high_str:
            try:
                last_high_date = datetime.strptime(last_high_str, '%Y-%m-%d').date()
                days_stalled = (today - last_high_date).days
                if days_stalled >= 7:
                    exit_price = round(ltp * (1 - self.SPREAD_FACTOR), 2)
                    return position, {
                        'should_exit': True,
                        'reason': 'Stall Exit - No new high in 7+ days',
                        'exit_price': exit_price
                    }
            except ValueError:
                pass

        # Step D: Hard exit — trailing stop hit
        current_sl = position.get('current_sl', position.get('stop_loss', 0))
        if ltp <= current_sl:
            exit_price = round(ltp * (1 - self.SPREAD_FACTOR), 2)
            return position, {
                'should_exit': True,
                'reason': 'Trailing Stop Hit',
                'exit_price': exit_price
            }

        return position, None

    def monitor_positions(self):
        """Background check: update trailing stops and auto-close when triggered."""
        with self._lock:
            positions = self._data['active_positions']
            if not positions:
                return []

            symbols = [p['symbol'] for p in positions]
            try:
                ltps = self._fetch_ltps(symbols)
            except Exception:
                return []

        # Update exit levels and identify positions to close
        to_close = []
        for i, p in enumerate(positions):
            ltp = ltps.get(p['symbol'])
            if ltp is None:
                continue

            updated_pos, exit_signal = self.update_exit_levels(p, ltp)

            # Update position in data (trailing SL, high-water mark)
            with self._lock:
                if i < len(self._data['active_positions']):
                    self._data['active_positions'][i] = updated_pos

            if exit_signal and exit_signal['should_exit']:
                to_close.append((p['trade_id'], exit_signal['exit_price'], exit_signal['reason']))

        # Save updated positions (ratcheted SLs)
        with self._lock:
            self._save_data()

        # Close triggered positions
        closed = []
        for trade_id, exit_price, reason in to_close:
            result = self.close_position(trade_id, exit_price, reason)
            if result.get('success'):
                closed.append(result)
                print(f"[Simulator] Auto-closed: {result['message']}")

        return closed

    def _migrate_position_to_trailing(self, position):
        """Migrate old-format position (fixed SL/target) to trailing stop format."""
        entry_price = position['entry_price']
        old_sl = position.get('stop_loss', entry_price * 0.95)

        # Reverse-engineer ATR from old SL: SL = entry - 1.5*ATR
        estimated_atr = round((entry_price - old_sl) / 1.5, 2) if entry_price > old_sl else round(entry_price * 0.03, 2)

        position['atr_at_entry'] = estimated_atr
        position['current_sl'] = old_sl
        position['highest_price_seen'] = entry_price
        position['last_new_high_date'] = position['entry_time'].split(' ')[0]
        position['trail_multiplier'] = 1.5
        position['stop_loss'] = old_sl  # keep in sync
        return position

    def reset(self, initial_capital=100000.0):
        """Reset simulator to starting state."""
        with self._lock:
            self._data = {
                "account_summary": {
                    "initial_capital": initial_capital,
                    "current_balance": initial_capital,
                    "total_pnl": 0.0
                },
                "active_positions": [],
                "trade_history": []
            }
            self._save_data()
        with self._history_lock:
            self._price_history = []
            self._save_price_history()
        return {'success': True, 'message': f'Simulator reset with capital: {initial_capital}'}

    def get_account_summary(self):
        """Get current account summary."""
        with self._lock:
            return {**self._data['account_summary']}


def start_position_monitor(simulator, interval=15):
    """Start a daemon thread that monitors positions for SL/target hits and records price history."""
    def _monitor_loop():
        while True:
            time.sleep(interval)
            try:
                simulator.record_price_snapshot()
                simulator.monitor_positions()
            except Exception as e:
                print(f"[Simulator Monitor] Error: {e}")

    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()
    print(f"[Simulator] Position monitor started (interval: {interval}s)")
