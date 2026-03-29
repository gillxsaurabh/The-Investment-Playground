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

  audit_results: {
    success: true,
    total: 8,
    results: [
      { symbol: 'SBIN',      saved_at: '2026-03-28T09:12:00', data: { type: 'audit', symbol: 'SBIN',      quantity: 50, average_price: 785.0,  last_price: 831.2,  pnl: 2310.0,  pnl_percentage: 5.88,  health_score: 7.8, health_label: 'HEALTHY',  health_components: { technical: 2.4, fundamental: 1.8, relative_strength: 1.6, news: 1.2, position: 0.8 }, audit_verdict: 'HOLD',          key_risks: ['NPA levels elevated', 'Interest rate sensitivity'], key_positives: ['Strong retail growth', 'Government backing', 'Rural expansion'], ai_reasoning: 'SBIN shows solid technical momentum with price above all EMAs. Fundamentals are improving QoQ driven by retail segment. Hold for medium term.', news_score: 4, news_headlines: ['SBI Q3 profit up 35% YoY', 'RBI eases NPA provisioning norms'], rsi: 58.2, adx: 28.4, ema_20: 818.5, ema_50: 802.1, ema_200: 756.3, stock_3m_return: 8.4, nifty_3m_return: 3.2, sector_3m_return: 6.1, sector_5d_change: 1.2, roe: 17.2, debt_to_equity: 0.9, profit_declining_quarters: 0, sector: 'Banking', saved_at: '2026-03-28T09:12:00' } },
      { symbol: 'ICICIBANK', saved_at: '2026-03-28T09:12:00', data: { type: 'audit', symbol: 'ICICIBANK', quantity: 30, average_price: 1105.0, last_price: 1248.0, pnl: 4290.0,  pnl_percentage: 12.95, health_score: 8.5, health_label: 'HEALTHY',  health_components: { technical: 2.6, fundamental: 2.1, relative_strength: 1.8, news: 1.2, position: 0.8 }, audit_verdict: 'HOLD',          key_risks: ['Valuation premium', 'Loan book concentration'], key_positives: ['Best-in-class ROE', 'Strong NIM', 'Digital banking growth'], ai_reasoning: 'ICICIBANK is the standout holding with strong technicals and fundamentals. Above-sector RS and improving margins justify HOLD. No exit signals visible.', news_score: 4, news_headlines: ['ICICI Bank digital loans up 40%', 'NIM expanded to 4.5%'], rsi: 62.1, adx: 31.2, ema_20: 1224.0, ema_50: 1180.5, ema_200: 1050.2, stock_3m_return: 14.2, nifty_3m_return: 3.2, sector_3m_return: 6.1, sector_5d_change: 1.2, roe: 18.4, debt_to_equity: 0.7, profit_declining_quarters: 0, sector: 'Banking', saved_at: '2026-03-28T09:12:00' } },
      { symbol: 'TCS',       saved_at: '2026-03-28T09:12:00', data: { type: 'audit', symbol: 'TCS',       quantity: 5,  average_price: 3820.0, last_price: 4156.0, pnl: 1680.0,  pnl_percentage: 8.80,  health_score: 7.2, health_label: 'STABLE',   health_components: { technical: 2.1, fundamental: 2.2, relative_strength: 1.2, news: 0.9, position: 0.8 }, audit_verdict: 'HOLD',          key_risks: ['US recession fears', 'Slower deal signings'], key_positives: ['Market leader position', 'Strong dividend yield', 'Consistent execution'], ai_reasoning: 'TCS has strong fundamentals but muted RS vs Nifty in recent 3 months. Revenue growth is stabilizing. Hold given quality, but watch for macro headwinds.', news_score: 3, news_headlines: ['TCS Q4 deal wins below estimates', 'Management guidance cautious for FY27'], rsi: 54.8, adx: 22.1, ema_20: 4098.0, ema_50: 3950.3, ema_200: 3680.1, stock_3m_return: 5.1, nifty_3m_return: 3.2, sector_3m_return: 7.4, sector_5d_change: 0.8, roe: 52.3, debt_to_equity: 0.0, profit_declining_quarters: 0, sector: 'IT', saved_at: '2026-03-28T09:12:00' } },
      { symbol: 'RELIANCE',  saved_at: '2026-03-28T09:12:00', data: { type: 'audit', symbol: 'RELIANCE',  quantity: 10, average_price: 2450.0, last_price: 2612.5, pnl: 1625.0,  pnl_percentage: 6.63,  health_score: 6.8, health_label: 'STABLE',   health_components: { technical: 1.9, fundamental: 2.0, relative_strength: 1.2, news: 0.9, position: 0.8 }, audit_verdict: 'MONITOR',       key_risks: ['Telecom ARPU growth slowing', 'Retail margin pressure'], key_positives: ['Jio 5G rollout ongoing', 'Strong balance sheet', 'Diversified revenue'], ai_reasoning: 'RELIANCE is stable but showing some technical weakness. EMA50 support is being tested. Monitor closely for next quarterly results before adding exposure.', news_score: 3, news_headlines: ['Reliance Jio ARPU growth slows to 3%', 'Retail segment EBITDA margin narrows'], rsi: 49.2, adx: 19.8, ema_20: 2588.0, ema_50: 2598.4, ema_200: 2410.2, stock_3m_return: 4.2, nifty_3m_return: 3.2, sector_3m_return: 5.0, sector_5d_change: 0.5, roe: 12.4, debt_to_equity: 0.4, profit_declining_quarters: 1, sector: 'Conglomerate', saved_at: '2026-03-28T09:12:00' } },
      { symbol: 'HCLTECH',   saved_at: '2026-03-28T09:12:00', data: { type: 'audit', symbol: 'HCLTECH',   quantity: 12, average_price: 1395.0, last_price: 1527.5, pnl: 1590.0,  pnl_percentage: 9.50,  health_score: 6.2, health_label: 'STABLE',   health_components: { technical: 1.8, fundamental: 1.8, relative_strength: 1.0, news: 0.9, position: 0.7 }, audit_verdict: 'MONITOR',       key_risks: ['IT spending slowdown', 'High client concentration'], key_positives: ['Strong engineering services', 'Products segment growing', 'Good dividend yield'], ai_reasoning: 'HCL Tech is holding well but relative strength vs IT sector peers is lagging. Fundamentals remain decent. Monitor for breakout above EMA20 resistance.', news_score: 3, news_headlines: ['HCL Tech Q3 margins in-line', 'New $200M deal win announced'], rsi: 52.4, adx: 20.5, ema_20: 1542.0, ema_50: 1498.2, ema_200: 1382.5, stock_3m_return: 3.8, nifty_3m_return: 3.2, sector_3m_return: 7.4, sector_5d_change: 0.8, roe: 24.8, debt_to_equity: 0.1, profit_declining_quarters: 0, sector: 'IT', saved_at: '2026-03-28T09:12:00' } },
      { symbol: 'BAJFINANCE',saved_at: '2026-03-28T09:12:00', data: { type: 'audit', symbol: 'BAJFINANCE',quantity: 4,  average_price: 6920.0, last_price: 7451.5, pnl: 2126.0,  pnl_percentage: 7.69,  health_score: 5.8, health_label: 'STABLE',   health_components: { technical: 1.6, fundamental: 1.9, relative_strength: 0.9, news: 0.6, position: 0.8 }, audit_verdict: 'MONITOR',       key_risks: ['RBI scrutiny on NBFC', 'Rising credit costs', 'Slowdown in consumer lending'], key_positives: ['Strong AUM growth', 'Premium franchise', 'Digital lending leadership'], ai_reasoning: 'BAJFINANCE is under regulatory pressure per recent news. Technical picture weakening with RSI below 50. Monitor closely — exit if price breaks EMA200 support.', news_score: 2, news_headlines: ['RBI issues show-cause notice to Bajaj Finance', 'NBFC credit costs rising in Q4'], rsi: 47.8, adx: 24.2, ema_20: 7512.0, ema_50: 7248.3, ema_200: 6842.1, stock_3m_return: 2.1, nifty_3m_return: 3.2, sector_3m_return: 6.1, sector_5d_change: 1.2, roe: 22.1, debt_to_equity: 3.8, profit_declining_quarters: 1, sector: 'NBFC', saved_at: '2026-03-28T09:12:00' } },
      { symbol: 'HDFCBANK',  saved_at: '2026-03-28T09:12:00', data: { type: 'audit', symbol: 'HDFCBANK',  quantity: 15, average_price: 1680.0, last_price: 1632.4, pnl: -714.0,  pnl_percentage: -2.83, health_score: 4.2, health_label: 'WATCH',    health_components: { technical: 1.2, fundamental: 1.6, relative_strength: 0.6, news: 0.6, position: 0.2 }, audit_verdict: 'CONSIDER_EXIT', key_risks: ['NIM compression post merger', 'LCR compliance pressure', 'Underperforming peers'], key_positives: ['Strong franchise value', 'Improving CASA ratio', 'Merger synergies long-term'], ai_reasoning: 'HDFCBANK is in WATCH territory. The HDFC merger integration is compressing margins and the stock is underperforming the banking index. Consider partial exit near current levels.', news_score: 2, news_headlines: ['HDFC Bank NIM contracts 20bps QoQ', 'LCR below RBI guideline — remedial action underway'], rsi: 42.1, adx: 18.2, ema_20: 1658.0, ema_50: 1692.4, ema_200: 1621.8, stock_3m_return: -1.8, nifty_3m_return: 3.2, sector_3m_return: 6.1, sector_5d_change: 1.2, roe: 14.2, debt_to_equity: 1.2, profit_declining_quarters: 2, sector: 'Banking', saved_at: '2026-03-28T09:12:00' } },
      { symbol: 'INFY',      saved_at: '2026-03-28T09:12:00', data: { type: 'audit', symbol: 'INFY',      quantity: 25, average_price: 1520.0, last_price: 1487.3, pnl: -817.5,  pnl_percentage: -2.15, health_score: 3.4, health_label: 'WATCH',    health_components: { technical: 0.8, fundamental: 1.4, relative_strength: 0.4, news: 0.6, position: 0.2 }, audit_verdict: 'CONSIDER_EXIT', key_risks: ['Guidance cut risk', 'US banking client exposures', 'Attrition still elevated'], key_positives: ['Strong cash generation', 'Dividend yield attractive', 'Large deal wins pipeline'], ai_reasoning: 'INFY is technically weak, trading below EMA50 and EMA200. Multiple guidance cuts and US client slowdown are material risks. Consider exiting on any bounce toward EMA50 resistance.', news_score: 2, news_headlines: ['Infosys cuts revenue guidance for Q4', 'US banking vertical contracts shrink 8%'], rsi: 38.4, adx: 26.8, ema_20: 1512.0, ema_50: 1552.3, ema_200: 1498.7, stock_3m_return: -3.4, nifty_3m_return: 3.2, sector_3m_return: 7.4, sector_5d_change: 0.8, roe: 31.2, debt_to_equity: 0.0, profit_declining_quarters: 2, sector: 'IT', saved_at: '2026-03-28T09:12:00' } },
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
