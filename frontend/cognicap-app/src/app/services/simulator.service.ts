import { Injectable, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, Subscription, interval, of } from 'rxjs';
import { switchMap, catchError, tap, map } from 'rxjs/operators';

export interface SimulatorPosition {
  trade_id: string;
  symbol: string;
  instrument_token?: number;
  entry_price: number;
  quantity: number;
  atr_at_entry: number;
  current_sl: number;
  highest_price_seen: number;
  last_new_high_date: string;
  trail_multiplier: number;
  stop_loss?: number;  // backward compat alias for current_sl
  target?: number;     // deprecated, not used in trailing system
  entry_time: string;
  status: string;
  ltp?: number;
  unrealized_pnl?: number;
}

export interface SimulatorAccount {
  initial_capital: number;
  current_balance: number;
  total_pnl: number;
  unrealized_pnl?: number;
}

export interface SimulatorState {
  success: boolean;
  account_summary: SimulatorAccount;
  positions: SimulatorPosition[];
  trade_history: SimulatorTradeHistory[];
  error?: string;
}

export interface SimulatorTradeHistory {
  trade_id: string;
  symbol: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  current_sl?: number;
  stop_loss?: number;
  target?: number;
  entry_time: string;
  exit_time: string;
  realized_pnl: number;
  reason: string;
  status: string;
}

export interface ExecuteOrderResponse {
  success: boolean;
  trade_id?: string;
  symbol?: string;
  entry_price?: number;
  quantity?: number;
  total_cost?: number;
  message?: string;
  error?: string;
}

export interface PriceSnapshotValue {
  pct: number;
  ltp: number;
  entry_price: number;
  stop_loss: number;  // current trailing SL value
  highest_price_seen: number;
  unrealized_pnl: number;
  quantity: number;
}

export interface PriceSnapshot {
  time: string;
  values: { [symbol: string]: PriceSnapshotValue };
}

export interface PriceHistoryResponse {
  success: boolean;
  history: PriceSnapshot[];
  error?: string;
}

export interface ClosePositionResponse {
  success: boolean;
  trade_id?: string;
  symbol?: string;
  exit_price?: number;
  realized_pnl?: number;
  reason?: string;
  message?: string;
  error?: string;
}

export interface SectorEntry {
  name: string;
  thesis: string;
  catalyst: string;
  conviction: number;
}

export interface SectorLeaderboardResponse {
  success: boolean;
  sectors?: SectorEntry[];
  researched_at?: string;
  error?: string;
}

export interface AutomationStockSummary {
  symbol: string;
  gear: number;
  gear_label: string;
  final_rank: number;
  composite_score: number;
  ai_conviction: number;
}

export interface AutomationRunRecord {
  run_id: string;
  date: string;
  started_at: string;
  completed_at: string;
  previous_positions_still_open: number;
  stocks_to_buy: number;
  stocks_selected: AutomationStockSummary[];
  trades_executed: number;
  trade_results: any[];
  mode?: string;
  status: 'completed' | 'skipped' | 'error' | 'dry_run';
  reason?: string;
  error?: string | null;
}

export interface AutomationStatus {
  success: boolean;
  enabled: boolean;
  mode: 'simulator' | 'live';
  scheduler_running: boolean;
  next_run: string | null;
  last_run: AutomationRunRecord | null;
}

@Injectable({
  providedIn: 'root'
})
export class SimulatorService implements OnDestroy {
  private apiUrl = 'http://localhost:5000/api/simulator';
  private tradingApiUrl = 'http://localhost:5000/api/trading';

  private stateSubject = new BehaviorSubject<SimulatorState | null>(null);
  public state$ = this.stateSubject.asObservable();

  private tradingModeSubject = new BehaviorSubject<'simulator' | 'live'>('simulator');
  public tradingMode$ = this.tradingModeSubject.asObservable();

  private pollingSubscription: Subscription | null = null;
  private pollingActive = false;

  constructor(private http: HttpClient) {
    this.loadTradingMode();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  private getToken(): string {
    return localStorage.getItem('access_token') || '';
  }

  private loadTradingMode(): void {
    this.http.get<{ success: boolean; mode: string }>(`${this.tradingApiUrl}/mode`)
      .pipe(catchError(() => of({ success: false, mode: 'simulator' })))
      .subscribe(res => {
        if (res.success) {
          this.tradingModeSubject.next(res.mode as 'simulator' | 'live');
        }
      });
  }

  getTradingMode(): 'simulator' | 'live' {
    return this.tradingModeSubject.value;
  }

  setTradingMode(mode: 'simulator' | 'live', confirm = false): Observable<any> {
    return this.http.post(`${this.tradingApiUrl}/mode`, { mode, confirm }).pipe(
      tap((res: any) => {
        if (res.success) {
          this.tradingModeSubject.next(mode);
        }
      })
    );
  }

  executeOrder(
    symbol: string,
    quantity: number,
    atr: number,
    trailMultiplier: number = 1.5,
    instrumentToken?: number,
    ltp?: number
  ): Observable<ExecuteOrderResponse> {
    return this.http.post<ExecuteOrderResponse>(`${this.apiUrl}/execute`, {
      access_token: this.getToken(),
      symbol,
      quantity,
      atr,
      trail_multiplier: trailMultiplier,
      instrument_token: instrumentToken,
      ltp
    }).pipe(
      tap(() => this.refreshPositions())
    );
  }

  computeTrailStatus(position: SimulatorPosition): 'RUNAWAY' | 'HOLDING' | 'CRITICAL' | 'STALLED' {
    const ltp = Number(position.ltp || position.entry_price);
    const entry = Number(position.entry_price);
    const sl = Number(position.current_sl ?? position.stop_loss ?? 0);
    const pnlPct = entry > 0 ? ((ltp - entry) / entry) * 100 : 0;
    const distToSlPct = ltp > 0 ? ((ltp - sl) / ltp) * 100 : 0;

    // Check days since last high for stall
    if (position.last_new_high_date) {
      const lastHighDate = new Date(position.last_new_high_date);
      const now = new Date();
      const daysSinceHigh = Math.floor((now.getTime() - lastHighDate.getTime()) / (1000 * 60 * 60 * 24));
      if (daysSinceHigh > 5) return 'STALLED';
    }

    // Critical: dangerously close to stop loss
    if (distToSlPct <= 0.5) return 'CRITICAL';

    // Runaway: in profit with healthy distance
    if (pnlPct > 0 && distToSlPct > 2.0) return 'RUNAWAY';

    // Holding: in loss but still has buffer
    if (pnlPct < 0 && distToSlPct > 0.5) return 'HOLDING';

    // Default: in profit but tight, or break-even
    return 'RUNAWAY';
  }

  getPositions(): Observable<SimulatorState> {
    return this.http.post<SimulatorState>(`${this.apiUrl}/positions`, {
      access_token: this.getToken()
    }).pipe(
      tap(state => this.stateSubject.next(state))
    );
  }

  closePosition(tradeId: string): Observable<ClosePositionResponse> {
    return this.http.post<ClosePositionResponse>(`${this.apiUrl}/close`, {
      access_token: this.getToken(),
      trade_id: tradeId
    }).pipe(
      tap(() => this.refreshPositions())
    );
  }

  resetSimulator(initialCapital: number = 100000): Observable<any> {
    return this.http.post(`${this.apiUrl}/reset`, {
      access_token: this.getToken(),
      initial_capital: initialCapital
    }).pipe(
      tap(() => this.refreshPositions())
    );
  }

  getPriceHistory(minutes: number = 60): Observable<PriceHistoryResponse> {
    return this.http.post<PriceHistoryResponse>(`${this.apiUrl}/price-history`, {
      access_token: this.getToken(),
      minutes,
    });
  }

  startPolling(intervalMs: number = 10000): void {
    if (this.pollingActive) return;
    this.pollingActive = true;

    // Initial fetch
    this.refreshPositions();

    this.pollingSubscription = interval(intervalMs).pipe(
      switchMap(() => this.getPositions().pipe(
        catchError(() => of(null))
      ))
    ).subscribe();
  }

  stopPolling(): void {
    this.pollingActive = false;
    if (this.pollingSubscription) {
      this.pollingSubscription.unsubscribe();
      this.pollingSubscription = null;
    }
  }

  researchSectors(): Observable<SectorLeaderboardResponse> {
    return this.http.post<SectorLeaderboardResponse>(
      'http://localhost:5000/api/sector-research/top-sectors', {}
    );
  }

  getAutomationStatus(): Observable<AutomationStatus> {
    return this.http.get<AutomationStatus>('http://localhost:5000/api/automation/status');
  }

  enableAutomation(enabled: boolean, mode: 'simulator' | 'live' = 'simulator'): Observable<any> {
    return this.http.post('http://localhost:5000/api/automation/enable', { enabled, mode });
  }

  runAutomationNow(accessToken: string, dryRun: boolean = true): Observable<any> {
    return this.http.post('http://localhost:5000/api/automation/run-now', {
      access_token: accessToken,
      dry_run: dryRun,
    });
  }

  getAutomationHistory(): Observable<{ success: boolean; history: AutomationRunRecord[] }> {
    return this.http.get<{ success: boolean; history: AutomationRunRecord[] }>(
      'http://localhost:5000/api/automation/history'
    );
  }

  private refreshPositions(): void {
    this.getPositions().pipe(
      catchError(() => of(null))
    ).subscribe();
  }
}
