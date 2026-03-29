import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface Holdings {
  success: boolean;
  holdings?: any[];
  error?: string;
}

export interface PortfolioSummary {
  success: boolean;
  summary?: {
    total_holdings: number;
    total_investment: number;
    current_value: number;
    total_pnl: number;
    pnl_percentage: number;
    positions_count: number;
  };
  error?: string;
  note?: string;
}

export interface TopPerformer {
  tradingsymbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  pnl_percentage: number;
}

export interface TopPerformers {
  success: boolean;
  top_gainers?: TopPerformer[];
  top_losers?: TopPerformer[];
  error?: string;
}

export interface MarketIndex {
  name: string;
  value: number;
  change: number;
  change_percent: number;
  high: number;
  low: number;
  volume: number;
}

export interface MarketIndices {
  success: boolean;
  nifty?: MarketIndex;
  sensex?: MarketIndex;
  error?: string;
}

export interface Stock {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  high: number;
  low: number;
}

export interface TopStocks {
  success: boolean;
  top_gainers?: Stock[];
  top_losers?: Stock[];
  error?: string;
}

export interface TradeExitResponse {
  success: boolean;
  symbol?: string;
  ltp?: number;
  atr?: number;
  initial_sl?: number;
  trail_multiplier?: number;
  risk_per_share?: number;
  error?: string;
}

export interface FundsResponse {
  success: boolean;
  available_funds?: number;
  error?: string;
}

// ── Stock Audit interfaces ────────────────────────────────────────────────

export interface AuditHealthComponents {
  technical: number;
  fundamental: number;
  relative_strength: number;
  news: number;
  position: number;
}

export interface AuditHolding {
  symbol: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  pnl_percentage: number;
  health_score: number;
  health_label: 'HEALTHY' | 'STABLE' | 'WATCH' | 'CRITICAL';
  health_components: AuditHealthComponents;
  audit_verdict: 'HOLD' | 'MONITOR' | 'CONSIDER_EXIT' | 'EXIT';
  key_risks: string[];
  key_positives: string[];
  ai_reasoning: string;
  news_score: number;
  news_headlines: string[];
  rsi: number | null;
  adx: number | null;
  ema_20: number | null;
  ema_50: number | null;
  ema_200: number | null;
  stock_3m_return: number | null;
  nifty_3m_return: number | null;
  sector_3m_return: number | null;
  sector_5d_change: number | null;
  roe: number | null;
  debt_to_equity: number | null;
  profit_declining_quarters: number;
  sector: string;
  saved_at?: string;
}

export interface AuditSummary {
  total: number;
  healthy: number;
  stable: number;
  watch: number;
  critical: number;
  avg_score: number;
}

export interface AuditResultsResponse {
  success: boolean;
  results: Array<{ symbol: string; saved_at: string; data: AuditHolding }>;
  total: number;
}

// ── Legacy health report interface (kept for backward compat) ─────────────

export interface HealthReport {
  symbol: string;
  company_name: string;
  current_price: number;
  quantity: number;
  investment: number;
  current_value: number;
  pnl: number;
  overall_score: number;
  breakdown: {
    momentum_score: number;
    momentum_detail: string;
    trend_score: number;
    trend_strength: string;
    trend_direction: string;
    fundamental_score: number;
    fundamental_health: string;
    ai_score: number;
    ai_summary: string;
  };
  last_updated: string;
  error?: string;
}

export interface HealthReportResponse {
  success: boolean;
  reports?: HealthReport[];
  total_stocks?: number;
  generated_at?: string;
  error?: string;
}

export interface AgentResult {
  score: number;
  explanation: string;
}

export interface StockAnalysisResponse {
  success: boolean;
  symbol?: string;
  overall_score?: number;
  verdict?: string;
  agents?: {
    stats_agent: AgentResult;
    company_health_agent: AgentResult;
    breaking_news_agent: AgentResult;
  };
  agent_errors?: string[];
  analyzed_at?: string;
  error?: string;
  // Legacy fields for backward compatibility with cached results
  score?: number;
  details?: {
    recency: { score: number; detail: string; };
    trend: { score: number; strength: string; direction: string; };
    fundamentals: { score: number; summary: string; roe?: number; debt_to_equity?: number; sales_growth?: number; };
    ai_sentiment: { score: number; summary: string; };
  };
}

@Injectable({
  providedIn: 'root'
})
export class KiteService {
  private apiUrl = '/api';

  constructor(private http: HttpClient) {}

  // --- Portfolio ---

  getHoldings(): Observable<Holdings> {
    return this.http.get<Holdings>(`${this.apiUrl}/portfolio/holdings`);
  }

  getPortfolioSummary(): Observable<PortfolioSummary> {
    return this.http.get<PortfolioSummary>(`${this.apiUrl}/portfolio/summary`);
  }

  getTopPerformers(): Observable<TopPerformers> {
    return this.http.get<TopPerformers>(`${this.apiUrl}/portfolio/top-performers`);
  }

  getHealthReport(): Observable<HealthReportResponse> {
    return this.http.get<HealthReportResponse>(`${this.apiUrl}/portfolio/health-report`);
  }

  // --- Market ---

  getMarketIndices(): Observable<MarketIndices> {
    return this.http.get<MarketIndices>(`${this.apiUrl}/market/indices`).pipe(
      catchError(() => of({ success: false } as MarketIndices))
    );
  }

  getTopStocks(): Observable<TopStocks> {
    return this.http.get<TopStocks>(`${this.apiUrl}/market/top-stocks`).pipe(
      catchError(() => of({ success: false, top_gainers: [], top_losers: [] } as TopStocks))
    );
  }

  // --- Analysis ---

  analyzeStock(symbol: string, instrumentToken?: number): Observable<StockAnalysisResponse> {
    return this.http.post<StockAnalysisResponse>(`${this.apiUrl}/analyze-stock`, {
      symbol,
      instrument_token: instrumentToken
    });
  }

  analyzeAllStocks(): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/analyze-all`, {});
  }

  // --- Stock Audit ---

  getAuditResults(): Observable<AuditResultsResponse> {
    return this.http.get<AuditResultsResponse>(`${this.apiUrl}/audit/results`);
  }

  // Note: /api/audit/run uses SSE — not a standard Observable.
  // The dashboard component calls fetch() directly for SSE streaming.

  // --- Trade ---

  getAvailableFunds(): Observable<FundsResponse> {
    return this.http.get<FundsResponse>(`${this.apiUrl}/trade/funds`);
  }

  calculateExits(symbol: string, instrumentToken: number, ltp: number): Observable<TradeExitResponse> {
    return this.http.post<TradeExitResponse>(`${this.apiUrl}/trade/calculate-exits`, {
      symbol,
      instrument_token: instrumentToken,
      ltp
    });
  }
}
