import { Component, OnDestroy, OnInit, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { KiteService, MarketIndex, Stock } from '../../services/kite.service';
import { SimulatorService } from '../../services/simulator.service';
import { AuthService, User } from '../../services/auth.service';
import { DemoService } from '../../services/demo.service';
import { HeaderBannerComponent } from '../shared/header-banner/header-banner.component';
import { forkJoin, interval, Observable, Subscription } from 'rxjs';
import { map } from 'rxjs/operators';

interface PipelineStep {
  id: string;
  name: string;
  agentName: string;
  agentRole: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  stocksRemaining: number | null;
  previousCount: number | null;
  startedAt: Date | null;
  completedAt: Date | null;
  durationMs: number | null;
}

interface StockResult {
  symbol: string;
  instrument_token: number;
  current_price: number;
  rsi: number;
  rsi_trigger: string;
  sector: string;
  sector_5d_change: number;
  why_selected: string;
  ema_20: number;
  ema_200: number;
  stock_3m_return: number;
  nifty_3m_return: number;
  avg_volume_20d: number;
  adx?: number;
  roe?: number;
  debt_to_equity?: number;
  composite_score?: number;
  profit_yoy_growing?: boolean;
  ai_conviction?: number;
  news_sentiment?: number;
  news_flag?: 'warning' | 'clear';
  news_headlines?: string[];
  final_rank?: number;
  final_rank_score?: number;
  rank_reason?: string;
  primary_risk?: string;
}

interface SellResult {
  symbol: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  pnl_percentage: number;
  instrument_token: number;
  rsi: number | null;
  adx: number | null;
  sector?: string;
  sector_5d_change?: number | null;
  sell_urgency_score: number;
  sell_urgency_label: 'STRONG SELL' | 'SELL' | 'WATCH' | 'HOLD';
  sell_signals: string[];
  sell_ai_conviction?: number;
  sell_reason?: string;
  hold_reason?: string;
}

interface TradeDetails {
  symbol: string;
  ltp: number;
  atr: number;
  initialSl: number;
  trailMultiplier: number;
  riskPerShare: number;
  availableFunds: number;
  investmentAmount: number;
  quantity: number;
}

@Component({
  selector: 'app-discover',
  standalone: true,
  imports: [CommonModule, FormsModule, HeaderBannerComponent],
  templateUrl: './discover.component.html',
  styleUrls: ['./discover.component.scss']
})
export class DiscoverComponent implements OnInit, OnDestroy {
  // Pipeline steps (buy mode)
  pipelineSteps: PipelineStep[] = [
    { id: 'universe_filter', name: 'Market Scanner', agentName: 'Market Scanner', agentRole: 'Screens universe by volume, 200-EMA & relative strength vs Nifty', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
    { id: 'technical_setup', name: 'Quant Analyst', agentName: 'Quant Analyst', agentRole: 'Identifies RSI entry triggers with ADX trend confirmation', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
    { id: 'fundamentals', name: 'Fundamentals Analyst', agentName: 'Fundamentals Analyst', agentRole: 'Validates quarterly profit growth, ROE & debt levels via Screener.in', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
    { id: 'sector_health', name: 'Sector Momentum', agentName: 'Sector Momentum', agentRole: 'Confirms positive 5-day sector index tailwind via Kite API', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
    { id: 'ai_ranking', name: 'AI Conviction Engine', agentName: 'AI Conviction Engine', agentRole: 'Composite scoring + LLM news sentiment ranking', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
    { id: 'final_ranking', name: 'Portfolio Ranker', agentName: 'Portfolio Ranker', agentRole: 'Multi-factor final ranking with LLM rank explanations', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
  ];

  // Pipeline steps (sell mode)
  sellPipelineSteps: PipelineStep[] = [
    { id: 'portfolio_load', name: 'Portfolio Inspector', agentName: 'Portfolio Inspector', agentRole: 'Fetches live holdings from Zerodha Kite', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
    { id: 'technical_scan', name: 'Quant Analyst', agentName: 'Quant Analyst', agentRole: 'Computes RSI, ADX, EMA-20/50/200, ATR, 3M relative strength', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
    { id: 'fundamental_scan', name: 'Fundamentals Analyst', agentName: 'Fundamentals Analyst', agentRole: 'Scrapes Screener.in for quarterly profit trends, ROE, D/E', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
    { id: 'sector_check', name: 'Sector Monitor', agentName: 'Sector Monitor', agentRole: 'Measures 5-day sector index performance', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
    { id: 'sell_scoring', name: 'Sell Signal Engine', agentName: 'Sell Signal Engine', agentRole: 'Multi-factor sell urgency scoring with AI exit reasoning', status: 'pending', stocksRemaining: null, previousCount: null, startedAt: null, completedAt: null, durationMs: null },
  ];

  pipelineMode: 'buy' | 'sell' = 'buy';
  selectedGear = 3;
  selectedProvider: 'gemini' | 'claude' | 'openai' = 'claude';
  isRunning = false;
  isCompleted = false;
  pipelineMessage = '';

  stockResults: StockResult[] = [];
  sellResults: SellResult[] = [];

  // Strategy gear info
  readonly GEAR_INFO: Record<number, { label: string; description: string }> = {
    1: { label: 'Fortress', description: 'Maximum safety — large caps, deep dips only, strict fundamentals.' },
    2: { label: 'Cautious', description: 'Conservative picks — large caps with standard checks.' },
    3: { label: 'Balanced', description: 'Default strategy — broad universe, moderate filters.' },
    4: { label: 'Growth', description: 'Capital appreciation — shallow dips, relaxed fundamentals.' },
    5: { label: 'Turbo', description: 'Momentum plays — small caps, breakouts, no fundamental filter.' },
  };
  readonly GEAR_ICONS: Record<number, string> = {
    1: '🛡️', 2: '🧱', 3: '⚖️', 4: '🚀', 5: '🔥',
  };
  private readonly GEAR_COLORS: Record<number, string> = {
    1: '#22c55e', 2: '#2dd4bf', 3: '#3b82f6', 4: '#f97316', 5: '#ef4444',
  };

  getSliderColor(): string {
    return this.GEAR_COLORS[this.selectedGear] ?? this.GEAR_COLORS[3];
  }

  // Staging list
  stagingList: StockResult[] = [];
  expandedStock: string | null = null;

  // Trading mode
  tradingMode: 'simulator' | 'live' = 'simulator';
  showLiveModeConfirm = false;

  // Trade modal
  showTradeModal = false;
  tradeDetails: TradeDetails | null = null;
  isLoadingTrade = false;
  tradeError = '';
  tradingStock: StockResult | null = null;

  // Bulk trade modal
  showBulkTradeModal = false;
  bulkTradeLoading = false;
  bulkTradeExecuting = false;
  bulkTradeProgress: number | null = null;
  bulkTradeDetails: {
    availableFunds: number;
    perStockAllocation: number;
    stocks: Array<{ symbol: string; ltp: number; quantity: number; atr: number; status: 'pending' | 'success' | 'error'; instrument_token?: number; }>;
  } | null = null;

  // Market data
  user: User | null = null;
  brokerLinked = false;
  nifty: MarketIndex | null = null;
  sensex: MarketIndex | null = null;
  marketGainers: Stock[] = [];
  marketLosers: Stock[] = [];
  isMarketLoading = false;
  marketError = '';

  private abortController: AbortController | null = null;
  private marketRefreshSub: Subscription | null = null;

  private static readonly RESULTS_KEY = 'cognicap_discover_results';
  private static readonly SELL_RESULTS_KEY = 'cognicap_discover_sell_results';

  get activePipelineSteps(): PipelineStep[] {
    return this.pipelineMode === 'sell' ? this.sellPipelineSteps : this.pipelineSteps;
  }

  constructor(
    private router: Router,
    private ngZone: NgZone,
    private kiteService: KiteService,
    private simulatorService: SimulatorService,
    private authService: AuthService,
    private demoService: DemoService
  ) {}

  ngOnInit(): void {
    this.authService.user$.subscribe(u => { this.user = u; });
    this.authService.brokerLinked$.subscribe(l => { this.brokerLinked = l; });
    this.simulatorService.tradingMode$.subscribe(m => { this.tradingMode = m; });
    this.loadMarketData();
    this.marketRefreshSub = interval(30000).subscribe(() => this.loadMarketData());
    this.loadSavedResults();
  }

  ngOnDestroy(): void {
    this.cancelPipeline();
    this.marketRefreshSub?.unsubscribe();
  }

  private loadMarketData(): void {
    this.isMarketLoading = true;
    forkJoin({ indices: this.kiteService.getMarketIndices(), stocks: this.kiteService.getTopStocks() }).subscribe({
      next: r => {
        if (r.indices.success) { this.nifty = r.indices.nifty ?? null; this.sensex = r.indices.sensex ?? null; }
        if (r.stocks.success) { this.marketGainers = r.stocks.top_gainers ?? []; this.marketLosers = r.stocks.top_losers ?? []; }
        this.isMarketLoading = false;
      },
      error: () => { this.isMarketLoading = false; }
    });
  }

  private loadSavedResults(): void {
    try {
      const saved = sessionStorage.getItem(DiscoverComponent.RESULTS_KEY);
      if (saved) this.stockResults = JSON.parse(saved);
      const savedSell = sessionStorage.getItem(DiscoverComponent.SELL_RESULTS_KEY);
      if (savedSell) this.sellResults = JSON.parse(savedSell);
    } catch { /* ignore */ }
  }

  togglePipelineMode(mode: 'buy' | 'sell'): void {
    if (this.isRunning) return;
    this.pipelineMode = mode;
  }

  async startPipeline(): Promise<void> {
    if (this.demoService.isDemo) { this.demoService.showKitePrompt(); return; }
    this.isRunning = true;
    this.isCompleted = false;
    this.pipelineMessage = '';

    if (this.pipelineMode === 'buy') {
      this.stockResults = [];
      this.pipelineSteps.forEach(s => { s.status = 'pending'; s.stocksRemaining = null; s.previousCount = null; s.startedAt = null; s.completedAt = null; s.durationMs = null; });
    } else {
      this.sellResults = [];
      this.sellPipelineSteps.forEach(s => { s.status = 'pending'; s.stocksRemaining = null; s.previousCount = null; s.startedAt = null; s.completedAt = null; s.durationMs = null; });
    }

    this.abortController = new AbortController();
    const jwtToken = localStorage.getItem('jwt_access_token') || '';
    const endpoint = this.pipelineMode === 'buy' ? '/api/decision-support/run' : '/api/decision-support/sell';
    const body = this.pipelineMode === 'buy'
      ? JSON.stringify({ config: { gear: this.selectedGear, llm_provider: this.selectedProvider } })
      : JSON.stringify({ config: { llm_provider: this.selectedProvider } });

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${jwtToken}` },
        body,
        signal: this.abortController.signal,
      });

      if (!response.ok || !response.body) throw new Error(`Request failed: ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEventType = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith('data: ') && currentEventType) {
            try {
              const data = JSON.parse(line.slice(6));
              const evt = currentEventType;
              this.ngZone.run(() => this.handleEvent(evt, data));
            } catch { /* skip */ }
            currentEventType = '';
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        this.ngZone.run(() => { this.pipelineMessage = `Pipeline error: ${err.message}`; });
      }
    } finally {
      this.ngZone.run(() => { this.isRunning = false; this.isCompleted = true; });
    }
  }

  cancelPipeline(): void {
    if (this.abortController) { this.abortController.abort(); this.abortController = null; }
  }

  private handleEvent(event: string, data: any): void {
    const steps = this.pipelineMode === 'buy' ? this.pipelineSteps : this.sellPipelineSteps;
    switch (event) {
      case 'step_start': {
        const step = steps.find(s => s.id === data.step);
        if (step) { step.status = 'running'; step.startedAt = new Date(); if (data.agent_name) step.agentName = data.agent_name; }
        break;
      }
      case 'step_complete': {
        const step = steps.find(s => s.id === data.step);
        if (step) {
          step.status = 'completed';
          step.stocksRemaining = data.stocks_remaining ?? null;
          step.completedAt = new Date();
          step.durationMs = data.duration_ms ?? (step.startedAt ? Date.now() - step.startedAt.getTime() : null);
          if (data.initial_count && step.id === 'universe_filter') step.previousCount = data.initial_count;
        }
        // Set previous counts for next steps
        for (let i = 1; i < steps.length; i++) {
          if (steps[i - 1].stocksRemaining !== null && steps[i].previousCount === null) {
            steps[i].previousCount = steps[i - 1].stocksRemaining;
          }
        }
        break;
      }
      case 'step_error': {
        const step = steps.find(s => s.id === data.step);
        if (step) step.status = 'error';
        break;
      }
      case 'final_result':
        // Buy pipeline: { stocks: [...] }
        if (this.pipelineMode === 'buy' && Array.isArray(data.stocks)) {
          this.stockResults = data.stocks as StockResult[];
          try { sessionStorage.setItem(DiscoverComponent.RESULTS_KEY, JSON.stringify(this.stockResults)); } catch { /* ignore */ }
        }
        // Sell pipeline: { holdings: [...] }
        if (this.pipelineMode === 'sell' && Array.isArray(data.holdings)) {
          this.sellResults = data.holdings as SellResult[];
          try { sessionStorage.setItem(DiscoverComponent.SELL_RESULTS_KEY, JSON.stringify(this.sellResults)); } catch { /* ignore */ }
        }
        this.pipelineMessage = data.message || 'Pipeline complete.';
        break;
      case 'stock_result':
        // Fallback: handle per-stock events if backend sends them individually
        if (this.pipelineMode === 'buy' && data.symbol) {
          const existing = this.stockResults.findIndex(s => s.symbol === data.symbol);
          if (existing >= 0) this.stockResults[existing] = { ...this.stockResults[existing], ...data };
          else this.stockResults.push(data as StockResult);
          try { sessionStorage.setItem(DiscoverComponent.RESULTS_KEY, JSON.stringify(this.stockResults)); } catch { /* ignore */ }
        }
        break;
      case 'sell_result':
        if (this.pipelineMode === 'sell' && data.symbol) {
          const existing = this.sellResults.findIndex(s => s.symbol === data.symbol);
          if (existing >= 0) this.sellResults[existing] = { ...this.sellResults[existing], ...data };
          else this.sellResults.push(data as SellResult);
          try { sessionStorage.setItem(DiscoverComponent.SELL_RESULTS_KEY, JSON.stringify(this.sellResults)); } catch { /* ignore */ }
        }
        break;
      case 'pipeline_complete':
        this.pipelineMessage = data.message || 'Pipeline complete.';
        break;
    }
  }

  toggleStock(symbol: string): void {
    this.expandedStock = this.expandedStock === symbol ? null : symbol;
  }

  addToStaging(stock: StockResult): void {
    if (!this.stagingList.find(s => s.symbol === stock.symbol)) {
      this.stagingList.push(stock);
    }
  }

  removeFromStaging(symbol: string): void {
    this.stagingList = this.stagingList.filter(s => s.symbol !== symbol);
  }

  openTradeModal(stock: StockResult): void {
    this.tradingStock = stock;
    this.showTradeModal = true;
    this.tradeError = '';
    this.isLoadingTrade = true;
    this.kiteService.calculateExits(stock.symbol, stock.instrument_token, stock.current_price).subscribe({
      next: (res) => {
        if (res.success) {
          this.getFundsForMode().subscribe({
            next: (funds) => {
              const atr = res.atr ?? 0;
              const trail = res.trail_multiplier ?? 1.5;
              const riskPerShare = atr * trail;
              const riskBudget = funds * 0.02;
              const qty = riskPerShare > 0 ? Math.floor(riskBudget / riskPerShare) : 0;
              this.tradeDetails = {
                symbol: stock.symbol,
                ltp: res.ltp ?? stock.current_price,
                atr,
                initialSl: res.initial_sl ?? 0,
                trailMultiplier: trail,
                riskPerShare,
                availableFunds: funds,
                investmentAmount: qty * (res.ltp ?? stock.current_price),
                quantity: qty
              };
              this.isLoadingTrade = false;
            },
            error: () => { this.tradeError = 'Failed to load funds.'; this.isLoadingTrade = false; }
          });
        } else {
          this.tradeError = res.error || 'Failed to calculate trade parameters.';
          this.isLoadingTrade = false;
        }
      },
      error: () => { this.tradeError = 'Failed to calculate trade parameters.'; this.isLoadingTrade = false; }
    });
  }

  closeTradeModal(): void {
    this.showTradeModal = false;
    this.tradeDetails = null;
    this.tradingStock = null;
    this.tradeError = '';
  }

  executeTrade(): void {
    if (!this.tradeDetails || !this.tradingStock) return;
    const { symbol, quantity, atr, trailMultiplier, ltp } = this.tradeDetails;
    const token = this.tradingStock.instrument_token;
    this.simulatorService.executeOrder(symbol, quantity, atr, trailMultiplier, token, ltp).subscribe({
      next: (res) => {
        if (res.success) {
          this.closeTradeModal();
          this.removeFromStaging(symbol);
          this.router.navigate(['/positions']);
        } else {
          this.tradeError = res.error || 'Trade failed.';
        }
      },
      error: (err) => { this.tradeError = err.error?.error || 'Trade failed.'; }
    });
  }

  goToLogin(): void {
    this.demoService.exitDemo();
    this.router.navigate(['/login']);
  }

  getUrgencyClass(label: string): string {
    const map: Record<string, string> = { 'STRONG SELL': 'urgent-strong', 'SELL': 'urgent-sell', 'WATCH': 'urgent-watch', 'HOLD': 'urgent-hold' };
    return map[label] || '';
  }

  formatNum(n: number | null | undefined): string {
    if (n == null) return '—';
    if (Math.abs(n) >= 1e7) return (n / 1e7).toFixed(1) + 'Cr';
    if (Math.abs(n) >= 1e5) return (n / 1e5).toFixed(1) + 'L';
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toFixed(0);
  }

  /** Returns simulator virtual balance in sim mode, real Kite funds in live mode. */
  private getFundsForMode(): Observable<number> {
    if (this.tradingMode === 'simulator') {
      return this.simulatorService.getPositions().pipe(
        map(state => state.account_summary?.current_balance ?? 1_000_000)
      );
    }
    return this.kiteService.getAvailableFunds().pipe(
      map(res => res.available_funds ?? 0)
    );
  }

  isStaged(symbol: string): boolean {
    return !!this.stagingList.find(s => s.symbol === symbol);
  }

  switchToLive(): void {
    this.simulatorService.setTradingMode('live', true).subscribe({
      next: () => { this.showLiveModeConfirm = false; },
      error: () => {}
    });
  }

  switchToSimulator(): void {
    this.simulatorService.setTradingMode('simulator').subscribe({ error: () => {} });
  }

  openBulkTradeModal(): void {
    this.showBulkTradeModal = true;
    this.bulkTradeLoading = true;
    this.bulkTradeDetails = null;

    this.getFundsForMode().subscribe({
      next: funds => {
        const riskBudget = funds * 0.02;
        const stocks: Array<{ symbol: string; ltp: number; quantity: number; atr: number; status: 'pending' | 'success' | 'error'; instrument_token?: number }> = [];

        let remaining = this.stagingList.length;
        const checkDone = () => {
          if (--remaining === 0) {
            this.bulkTradeDetails = { availableFunds: funds, perStockAllocation: riskBudget, stocks };
            this.bulkTradeLoading = false;
          }
        };

        for (const s of this.stagingList) {
          this.kiteService.calculateExits(s.symbol, s.instrument_token, s.current_price).subscribe({
            next: res => {
              if (res.success) {
                const atr = res.atr ?? 0;
                const trail = res.trail_multiplier ?? 1.5;
                const riskPerShare = atr * trail;
                const qty = riskPerShare > 0 ? Math.floor(riskBudget / riskPerShare) : 0;
                stocks.push({ symbol: s.symbol, ltp: res.ltp ?? s.current_price, quantity: qty, atr, status: 'pending', instrument_token: s.instrument_token });
              }
              checkDone();
            },
            error: () => checkDone()
          });
        }
      },
      error: () => { this.bulkTradeLoading = false; }
    });
  }

  executeAllTrades(): void {
    if (!this.bulkTradeDetails) return;
    this.bulkTradeExecuting = true;
    this.bulkTradeProgress = 0;

    const doNext = (i: number) => {
      if (!this.bulkTradeDetails || i >= this.bulkTradeDetails.stocks.length) {
        this.bulkTradeExecuting = false;
        const successSymbols = (this.bulkTradeDetails?.stocks ?? []).filter(s => s.status === 'success').map(s => s.symbol);
        successSymbols.forEach(sym => this.removeFromStaging(sym));
        if (successSymbols.length > 0) {
          setTimeout(() => { this.closeBulkModal(); this.router.navigate(['/positions']); }, 1200);
        }
        return;
      }
      const s = this.bulkTradeDetails.stocks[i];
      this.simulatorService.executeOrder(s.symbol, s.quantity, s.atr, 1.5, s.instrument_token, s.ltp).subscribe({
        next: res => { s.status = res.success ? 'success' : 'error'; this.bulkTradeProgress = i + 1; doNext(i + 1); },
        error: () => { s.status = 'error'; this.bulkTradeProgress = i + 1; doNext(i + 1); }
      });
    };
    doNext(0);
  }

  closeBulkModal(): void {
    if (this.bulkTradeExecuting) return;
    this.showBulkTradeModal = false;
    this.bulkTradeDetails = null;
    this.bulkTradeProgress = null;
  }
}
