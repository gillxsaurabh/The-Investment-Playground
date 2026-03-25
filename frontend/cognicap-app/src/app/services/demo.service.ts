import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

// ── All static demo data ────────────────────────────────────────────────────

export const DEMO_DATA = {
  user: { name: 'Arjun Sharma', email: 'arjun@tip.in', user_id: 'ZY8821' },

  portfolio_summary: {
    success: true,
    summary: {
      total_holdings: 8,
      total_investment: 243710,
      current_value: 256100,
      total_pnl: 12390,
      pnl_percentage: 5.08,
      positions_count: 0,
    },
  },

  holdings: {
    success: true,
    holdings: [
      { tradingsymbol: 'RELIANCE', exchange: 'NSE', quantity: 10, average_price: 2450.0, last_price: 2612.5, pnl: 1625.0, day_change: 20.8, day_change_percentage: 0.80, instrument_token: 738561 },
      { tradingsymbol: 'INFY',     exchange: 'NSE', quantity: 25, average_price: 1520.0, last_price: 1487.3, pnl: -817.5, day_change: -5.9, day_change_percentage: -0.40, instrument_token: 408065 },
      { tradingsymbol: 'TCS',      exchange: 'NSE', quantity: 5,  average_price: 3820.0, last_price: 4156.0, pnl: 1680.0, day_change: 49.9, day_change_percentage: 1.22, instrument_token: 2953217 },
      { tradingsymbol: 'HDFCBANK', exchange: 'NSE', quantity: 15, average_price: 1680.0, last_price: 1632.4, pnl: -714.0, day_change: -4.9, day_change_percentage: -0.30, instrument_token: 341249 },
      { tradingsymbol: 'ICICIBANK',exchange: 'NSE', quantity: 30, average_price: 1105.0, last_price: 1248.0, pnl: 4290.0, day_change: 7.5,  day_change_percentage: 0.61, instrument_token: 1270529 },
      { tradingsymbol: 'BAJFINANCE',exchange:'NSE', quantity: 4,  average_price: 6920.0, last_price: 7451.5, pnl: 2126.0, day_change: 104.3,day_change_percentage: 1.42, instrument_token: 81153 },
      { tradingsymbol: 'HCLTECH',  exchange: 'NSE', quantity: 12, average_price: 1395.0, last_price: 1527.5, pnl: 1590.0, day_change: 13.7, day_change_percentage: 0.91, instrument_token: 1850625 },
      { tradingsymbol: 'SBIN',     exchange: 'NSE', quantity: 50, average_price: 785.0,  last_price: 831.2,  pnl: 2310.0, day_change: 4.2,  day_change_percentage: 0.51, instrument_token: 779521 },
    ],
  },

  top_performers: {
    success: true,
    top_gainers: [
      { tradingsymbol: 'ICICIBANK',  exchange: 'NSE', quantity: 30, average_price: 1105,  last_price: 1248.0, pnl: 4290,  pnl_percentage: 12.95 },
      { tradingsymbol: 'BAJFINANCE', exchange: 'NSE', quantity: 4,  average_price: 6920,  last_price: 7451.5, pnl: 2126,  pnl_percentage: 7.69 },
      { tradingsymbol: 'TCS',        exchange: 'NSE', quantity: 5,  average_price: 3820,  last_price: 4156.0, pnl: 1680,  pnl_percentage: 8.80 },
    ],
    top_losers: [
      { tradingsymbol: 'HDFCBANK', exchange: 'NSE', quantity: 15, average_price: 1680, last_price: 1632.4, pnl: -714,   pnl_percentage: -2.83 },
      { tradingsymbol: 'INFY',     exchange: 'NSE', quantity: 25, average_price: 1520, last_price: 1487.3, pnl: -817.5, pnl_percentage: -2.15 },
    ],
  },

  market_indices: {
    success: true,
    nifty:  { name: 'NIFTY 50', value: 23456.8, change: 182.4, change_percent: 0.78, high: 23510.2, low: 23280.5, volume: 248600000 },
    sensex: { name: 'SENSEX',   value: 77124.3, change: 612.5, change_percent: 0.80, high: 77350.8, low: 76582.1, volume: 0 },
  },

  top_stocks: {
    success: true,
    top_gainers: [
      { symbol: 'POWERGRID', name: 'Power Grid Corporation',  price: 342.8,  change: 10.7,  change_percent: 3.22, volume: 8542000,  high: 346.5,  low: 332.1 },
      { symbol: 'BHEL',      name: 'Bharat Heavy Electricals',price: 272.4,  change: 7.5,   change_percent: 2.84, volume: 12340000, high: 275.0,  low: 265.2 },
      { symbol: 'NTPC',      name: 'NTPC Limited',            price: 388.6,  change: 9.1,   change_percent: 2.40, volume: 6780000,  high: 392.0,  low: 380.1 },
      { symbol: 'COALINDIA', name: 'Coal India',              price: 442.9,  change: 8.8,   change_percent: 2.03, volume: 5230000,  high: 447.5,  low: 434.2 },
      { symbol: 'ONGC',      name: 'Oil & Natural Gas Corp',  price: 278.3,  change: 4.8,   change_percent: 1.75, volume: 9870000,  high: 281.0,  low: 273.5 },
    ],
    top_losers: [
      { symbol: 'PAYTM',    name: 'One97 Communications', price: 521.4,  change: -11.7, change_percent: -2.20, volume: 7890000,  high: 535.2,  low: 518.3 },
      { symbol: 'ZOMATO',   name: 'Zomato',               price: 218.6,  change: -4.0,  change_percent: -1.80, volume: 18920000, high: 225.1,  low: 216.8 },
      { symbol: 'INDIGO',   name: 'InterGlobe Aviation',  price: 4218.5, change: -47.3, change_percent: -1.11, volume: 342000,   high: 4285.0, low: 4195.2 },
      { symbol: 'TATACOMM', name: 'Tata Communications',  price: 1842.3, change: -18.2, change_percent: -0.98, volume: 234000,   high: 1872.5, low: 1838.0 },
      { symbol: 'JUBLFOOD', name: 'Jubilant FoodWorks',   price: 548.7,  change: -4.8,  change_percent: -0.87, volume: 1240000,  high: 556.3,  low: 546.2 },
    ],
  },

  simulator_state: {
    success: true,
    account_summary: {
      initial_capital: 500000,
      current_balance: 421480,
      total_pnl: 7640,
      unrealized_pnl: 4235,
    },
    positions: [
      {
        trade_id: 'SIM_180326_TATAMOTORS_4821', symbol: 'TATAMOTORS', instrument_token: 884737,
        entry_price: 912.4, quantity: 25, atr_at_entry: 28.5, current_sl: 848.2,
        highest_price_seen: 1024.6, last_new_high_date: '2026-03-20', trail_multiplier: 1.5,
        stop_loss: 848.2, entry_time: '2026-03-18 09:15:42', status: 'OPEN',
        ltp: 1024.6, unrealized_pnl: 2805.0,
      },
      {
        trade_id: 'SIM_180326_ADANIENT_7234', symbol: 'ADANIENT', instrument_token: 3861249,
        entry_price: 2948.5, quantity: 8, atr_at_entry: 92.3, current_sl: 2702.1,
        highest_price_seen: 3174.8, last_new_high_date: '2026-03-22', trail_multiplier: 1.5,
        stop_loss: 2702.1, entry_time: '2026-03-18 09:18:11', status: 'OPEN',
        ltp: 3174.8, unrealized_pnl: 1825.0,
      },
      {
        trade_id: 'SIM_180326_LTIMINDTREE_5567', symbol: 'LTIMINDTREE', instrument_token: 4752385,
        entry_price: 5450.0, quantity: 10, atr_at_entry: 145.2, current_sl: 5085.4,
        highest_price_seen: 5450.0, last_new_high_date: '2026-03-18', trail_multiplier: 1.5,
        stop_loss: 5085.4, entry_time: '2026-03-18 09:22:33', status: 'OPEN',
        ltp: 5210.5, unrealized_pnl: -2395.0,
      },
    ],
    trade_history: [
      {
        trade_id: 'SIM_100326_MOTHERSON_3312', symbol: 'MOTHERSON',
        entry_price: 142.3, exit_price: 158.7, quantity: 150,
        entry_time: '2026-03-10 09:14:22', exit_time: '2026-03-18 15:28:44',
        realized_pnl: 2460.0, reason: 'Manual Close', status: 'CLOSED',
      },
      {
        trade_id: 'SIM_100326_BHARTIARTL_8891', symbol: 'BHARTIARTL',
        entry_price: 1682.5, exit_price: 1624.8, quantity: 12,
        entry_time: '2026-03-10 09:18:55', exit_time: '2026-03-14 10:45:12',
        realized_pnl: -692.4, reason: 'Stop Loss Hit', status: 'CLOSED',
      },
      {
        trade_id: 'SIM_030326_JUBLFOOD_2245', symbol: 'JUBLFOOD',
        entry_price: 512.0, exit_price: 571.5, quantity: 30,
        entry_time: '2026-03-03 09:12:10', exit_time: '2026-03-10 14:22:38',
        realized_pnl: 1785.0, reason: 'Trailing Stop Hit', status: 'CLOSED',
      },
    ],
  },

  trading_mode: { success: true, mode: 'simulator' },

  automation_status: {
    success: true,
    enabled: true,
    mode: 'simulator',
    scheduler_running: true,
    next_run: '2026-03-31T09:00:00+05:30',
    last_run: {
      run_id: 'AUTO_20260324', date: '2026-03-24',
      started_at: '2026-03-24T09:00:12+05:30', completed_at: '2026-03-24T09:04:58+05:30',
      previous_positions_still_open: 2, stocks_to_buy: 4,
      stocks_selected: [
        { symbol: 'TATAMOTORS',  gear: 4, gear_label: 'Growth',   final_rank: 1, composite_score: 78, ai_conviction: 9 },
        { symbol: 'ADANIENT',    gear: 3, gear_label: 'Balanced',  final_rank: 2, composite_score: 74, ai_conviction: 8 },
        { symbol: 'LTIMINDTREE', gear: 3, gear_label: 'Balanced',  final_rank: 3, composite_score: 71, ai_conviction: 8 },
        { symbol: 'CAMS',        gear: 5, gear_label: 'Turbo',     final_rank: 4, composite_score: 68, ai_conviction: 7 },
      ],
      trades_executed: 3, trade_results: [], mode: 'simulator', status: 'completed',
    },
  },

  automation_history: {
    success: true,
    history: [
      {
        run_id: 'AUTO_20260324', date: '2026-03-24',
        started_at: '2026-03-24T09:00:12+05:30', completed_at: '2026-03-24T09:04:58+05:30',
        previous_positions_still_open: 2, stocks_to_buy: 4,
        stocks_selected: [
          { symbol: 'TATAMOTORS',  gear: 4, gear_label: 'Growth',  final_rank: 1, composite_score: 78, ai_conviction: 9 },
          { symbol: 'ADANIENT',    gear: 3, gear_label: 'Balanced', final_rank: 2, composite_score: 74, ai_conviction: 8 },
          { symbol: 'LTIMINDTREE', gear: 3, gear_label: 'Balanced', final_rank: 3, composite_score: 71, ai_conviction: 8 },
          { symbol: 'CAMS',        gear: 5, gear_label: 'Turbo',    final_rank: 4, composite_score: 68, ai_conviction: 7 },
        ],
        trades_executed: 3, trade_results: [], mode: 'simulator', status: 'completed',
      },
      {
        run_id: 'AUTO_20260317', date: '2026-03-17',
        started_at: '2026-03-17T09:00:08+05:30', completed_at: '2026-03-17T09:03:44+05:30',
        previous_positions_still_open: 0, stocks_to_buy: 6,
        stocks_selected: [
          { symbol: 'MOTHERSON', gear: 4, gear_label: 'Growth',   final_rank: 1, composite_score: 81, ai_conviction: 9 },
          { symbol: 'BHARTIARTL',gear: 3, gear_label: 'Balanced', final_rank: 2, composite_score: 75, ai_conviction: 8 },
          { symbol: 'JUBLFOOD',  gear: 4, gear_label: 'Growth',   final_rank: 3, composite_score: 72, ai_conviction: 8 },
          { symbol: 'NAUKRI',    gear: 3, gear_label: 'Balanced', final_rank: 5, composite_score: 67, ai_conviction: 7 },
          { symbol: 'TRENT',     gear: 3, gear_label: 'Balanced', final_rank: 6, composite_score: 65, ai_conviction: 7 },
          { symbol: 'VOLTAS',    gear: 3, gear_label: 'Balanced', final_rank: 7, composite_score: 63, ai_conviction: 6 },
        ],
        trades_executed: 6, trade_results: [], mode: 'simulator', status: 'completed',
      },
      {
        run_id: 'AUTO_20260310', date: '2026-03-10',
        started_at: '2026-03-10T09:00:15+05:30', completed_at: '2026-03-10T09:05:22+05:30',
        previous_positions_still_open: 3, stocks_to_buy: 3,
        stocks_selected: [
          { symbol: 'DELHIVERY', gear: 5, gear_label: 'Turbo',   final_rank: 1, composite_score: 76, ai_conviction: 8 },
          { symbol: 'VOLTAS',    gear: 3, gear_label: 'Balanced', final_rank: 2, composite_score: 71, ai_conviction: 7 },
          { symbol: 'ABCAPITAL', gear: 4, gear_label: 'Growth',  final_rank: 3, composite_score: 68, ai_conviction: 7 },
        ],
        trades_executed: 3, trade_results: [], mode: 'simulator', status: 'completed',
      },
      {
        run_id: 'AUTO_20260303', date: '2026-03-03',
        started_at: '2026-03-03T09:00:22+05:30', completed_at: '2026-03-03T09:06:11+05:30',
        previous_positions_still_open: 1, stocks_to_buy: 5,
        stocks_selected: [
          { symbol: 'JUBLFOOD',   gear: 4, gear_label: 'Growth',  final_rank: 1, composite_score: 80, ai_conviction: 9 },
          { symbol: 'TATAELXSI', gear: 3, gear_label: 'Balanced', final_rank: 2, composite_score: 74, ai_conviction: 8 },
          { symbol: 'CESC',       gear: 2, gear_label: 'Cautious', final_rank: 3, composite_score: 69, ai_conviction: 7 },
          { symbol: 'CASTROLIND',gear: 2, gear_label: 'Cautious', final_rank: 4, composite_score: 66, ai_conviction: 7 },
          { symbol: 'GRASIM',    gear: 3, gear_label: 'Balanced', final_rank: 5, composite_score: 62, ai_conviction: 6 },
        ],
        trades_executed: 5, trade_results: [], mode: 'simulator', status: 'completed',
      },
    ],
  },
};

// ── Service ─────────────────────────────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class DemoService {
  private _isDemo = new BehaviorSubject<boolean>(
    localStorage.getItem('demo_mode') === 'true'
  );
  public isDemo$ = this._isDemo.asObservable();

  private _showPrompt = new BehaviorSubject<boolean>(false);
  public showPrompt$ = this._showPrompt.asObservable();

  get isDemo(): boolean {
    return this._isDemo.value;
  }

  enterDemo(): void {
    localStorage.setItem('demo_mode', 'true');
    localStorage.setItem('user', JSON.stringify(DEMO_DATA.user));
    this._isDemo.next(true);
  }

  exitDemo(): void {
    localStorage.removeItem('demo_mode');
    localStorage.removeItem('user');
    this._isDemo.next(false);
  }

  showKitePrompt(): void {
    this._showPrompt.next(true);
  }

  hideKitePrompt(): void {
    this._showPrompt.next(false);
  }
}
