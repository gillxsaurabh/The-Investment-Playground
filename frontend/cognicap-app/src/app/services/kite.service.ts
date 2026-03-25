import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, of } from 'rxjs';
import { map, tap, catchError } from 'rxjs/operators';

export interface AuthResponse {
  success: boolean;
  access_token?: string;
  user?: {
    name: string;
    email: string;
    user_id: string;
  };
  error?: string;
}

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
  note?: string; // Optional note for simulation/debug info
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
  private apiUrl = 'http://localhost:5000/api';
  private accessTokenSubject = new BehaviorSubject<string | null>(this.getStoredToken());
  public accessToken$ = this.accessTokenSubject.asObservable();
  private userSubject = new BehaviorSubject<any>(this.getStoredUser());
  public user$ = this.userSubject.asObservable();

  constructor(private http: HttpClient) {}

  private getStoredToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private getStoredUser(): any {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  }

  getLoginUrl(): Observable<any> {
    return this.http.get(`${this.apiUrl}/auth/login-url`);
  }

  authenticate(requestToken: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.apiUrl}/auth/authenticate`, {
      request_token: requestToken
    }).pipe(
      tap(response => {
        if (response.success && response.access_token) {
          localStorage.setItem('access_token', response.access_token);
          localStorage.setItem('user', JSON.stringify(response.user));
          this.accessTokenSubject.next(response.access_token);
          this.userSubject.next(response.user);
        }
      })
    );
  }

  verifyToken(): Observable<boolean> {
    const token = this.getStoredToken();
    if (!token) {
      return new Observable(observer => {
        observer.next(false);
        observer.complete();
      });
    }

    return this.http.post<AuthResponse>(`${this.apiUrl}/auth/verify`, {
      access_token: token
    }).pipe(
      map(response => {
        if (response.success && response.user) {
          this.userSubject.next(response.user);
          return true;
        }
        return false;
      })
    );
  }

  getHoldings(): Observable<Holdings> {
    const token = this.getStoredToken();
    return this.http.post<Holdings>(`${this.apiUrl}/portfolio/holdings`, {
      access_token: token
    });
  }

  getPortfolioSummary(): Observable<PortfolioSummary> {
    const token = this.getStoredToken();
    return this.http.post<PortfolioSummary>(`${this.apiUrl}/portfolio/summary`, {
      access_token: token
    });
  }

  getTopPerformers(): Observable<TopPerformers> {
    const token = this.getStoredToken();
    return this.http.post<TopPerformers>(`${this.apiUrl}/portfolio/top-performers`, {
      access_token: token
    });
  }

  getMarketIndices(): Observable<MarketIndices> {
    const token = this.getStoredToken();
    return this.http.post<MarketIndices>(`${this.apiUrl}/market/indices`, {
      access_token: token
    }).pipe(catchError(() => of({ success: false } as MarketIndices)));
  }

  getTopStocks(): Observable<TopStocks> {
    const token = this.getStoredToken();
    return this.http.post<TopStocks>(`${this.apiUrl}/market/top-stocks`, {
      access_token: token
    }).pipe(catchError(() => of({ success: false, top_gainers: [], top_losers: [] } as TopStocks)));
  }

  getHealthReport(): Observable<HealthReportResponse> {
    const token = this.getStoredToken();
    return this.http.post<HealthReportResponse>(`${this.apiUrl}/portfolio/health-report`, {
      access_token: token
    });
  }

  analyzeStock(symbol: string, instrumentToken?: number): Observable<StockAnalysisResponse> {
    const token = this.getStoredToken();
    return this.http.post<StockAnalysisResponse>(`${this.apiUrl}/analyze-stock`, {
      access_token: token,
      symbol: symbol,
      instrument_token: instrumentToken
    });
  }

  analyzeAllStocks(): Observable<any> {
    const token = this.getStoredToken();
    return this.http.post<any>(`${this.apiUrl}/analyze-all`, {
      access_token: token
    });
  }

  getAvailableFunds(): Observable<FundsResponse> {
    const token = this.getStoredToken();
    return this.http.post<FundsResponse>(`${this.apiUrl}/trade/funds`, {
      access_token: token
    });
  }

  calculateExits(symbol: string, instrumentToken: number, ltp: number): Observable<TradeExitResponse> {
    const token = this.getStoredToken();
    return this.http.post<TradeExitResponse>(`${this.apiUrl}/trade/calculate-exits`, {
      access_token: token,
      symbol,
      instrument_token: instrumentToken,
      ltp
    });
  }

  logout(): void {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    this.accessTokenSubject.next(null);
    this.userSubject.next(null);
  }

  isAuthenticated(): boolean {
    return !!this.getStoredToken();
  }
}
