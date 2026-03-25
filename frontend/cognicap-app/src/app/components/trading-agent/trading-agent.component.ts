import { Component, OnDestroy, OnInit, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { KiteService, MarketIndex, Stock } from '../../services/kite.service';
import { SimulatorService, SimulatorState, SimulatorPosition, SimulatorTradeHistory, AutomationStatus, AutomationRunRecord } from '../../services/simulator.service';
import { DemoService } from '../../services/demo.service';
import { HeaderBannerComponent } from '../shared/header-banner/header-banner.component';
import { forkJoin, of, interval, Subscription } from 'rxjs';
import { PositionsChartComponent } from './positions-chart.component';

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
  logs: LogEntry[];
}

interface LogEntry {
  timestamp: Date;
  step: string;
  message: string;
  type: 'info' | 'success' | 'error';
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
  totalStocks: number;
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
  sector_3m_return?: number;
  avg_volume_20d: number;
  volume_ratio?: number;
  adx?: number;
  roe?: number;
  debt_to_equity?: number;
  composite_score?: number;
  score_breakdown?: {
    technical: number;
    fundamental: number;
    relative_strength: number;
    volume_health: number;
  };
  profit_yoy_growing?: boolean;
  ai_conviction?: number;
  news_sentiment?: number;
  news_flag?: 'warning' | 'clear';
  news_headlines?: string[];
  // Portfolio Ranker (Agent 6)
  final_rank?: number;
  final_rank_score?: number;
  rank_reason?: string;
  rank_factors?: {
    ai_conviction_norm: number;
    composite_score_norm: number;
    relative_strength_norm: number;
    fundamental_norm: number;
    sector_momentum_norm: number;
  };
  // Claude-only fields
  primary_risk?: string;
  trade_type?: string;
  portfolio_note?: string;
}

interface MarketRegime {
  vix: number | null;
  regime: string;
  warning: string | null;
}

interface SellScoreBreakdown {
  technical_breakdown: number;
  relative_weakness: number;
  fundamental_flags: number;
  position_health: number;
}

interface SellResult {
  symbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  pnl_percentage: number;
  instrument_token: number;
  current_price: number;
  rsi: number | null;
  adx: number | null;
  ema_20: number | null;
  ema_50: number | null;
  ema_200: number | null;
  atr: number | null;
  stock_3m_return: number | null;
  nifty_3m_return: number | null;
  sector?: string;
  sector_index?: string;
  sector_3m_return?: number;
  sector_5d_change?: number | null;
  avg_volume_20d: number | null;
  volume_ratio: number | null;
  roe?: number | null;
  debt_to_equity?: number | null;
  profit_declining_quarters?: number;
  qoq_declining?: boolean;
  yoy_declining?: boolean | null;
  sell_urgency_score: number;
  sell_urgency_label: 'STRONG SELL' | 'SELL' | 'WATCH' | 'HOLD';
  sell_signals: string[];
  sell_score_breakdown?: SellScoreBreakdown;
  sell_ai_conviction?: number;
  sell_reason?: string;
  hold_reason?: string;
  news_sentiment?: number;
  news_flag?: 'warning' | 'clear';
  news_headlines?: string[];
}

interface GearInfo {
  label: string;
  description: string;
}

@Component({
  selector: 'app-trading-agent',
  standalone: true,
  imports: [CommonModule, FormsModule, PositionsChartComponent, HeaderBannerComponent],
  templateUrl: './trading-agent.component.html',
  styleUrls: ['./trading-agent.component.scss']
})
export class TradingAgentComponent implements OnInit, OnDestroy {
  pipelineSteps: PipelineStep[] = [
    {
      id: 'universe_filter', name: 'Market Scanner',
      agentName: 'Market Scanner',
      agentRole: 'Screens universe by volume, 200-EMA & relative strength vs Nifty',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
    {
      id: 'technical_setup', name: 'Quant Analyst',
      agentName: 'Quant Analyst',
      agentRole: 'Identifies RSI entry triggers with ADX trend confirmation',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
    {
      id: 'fundamentals', name: 'Fundamentals Analyst',
      agentName: 'Fundamentals Analyst',
      agentRole: 'Validates quarterly profit growth, ROE & debt levels via Screener.in',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
    {
      id: 'sector_health', name: 'Sector Momentum',
      agentName: 'Sector Momentum',
      agentRole: 'Confirms positive 5-day sector index tailwind via Kite API',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
    {
      id: 'ai_ranking', name: 'AI Conviction Engine',
      agentName: 'AI Conviction Engine',
      agentRole: 'Composite scoring (Technical + Fundamental + RS + Volume) then LLM news sentiment ranking',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
    {
      id: 'final_ranking', name: 'Portfolio Ranker',
      agentName: 'Portfolio Ranker',
      agentRole: 'Multi-factor final ranking across all 5 pipeline signals with LLM rank explanations',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
  ];

  sellPipelineSteps: PipelineStep[] = [
    {
      id: 'portfolio_load', name: 'Portfolio Inspector',
      agentName: 'Portfolio Inspector',
      agentRole: 'Fetches live holdings from Zerodha Kite and resolves instrument tokens & sector mapping',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
    {
      id: 'technical_scan', name: 'Quant Analyst',
      agentName: 'Quant Analyst',
      agentRole: 'Fetches 400-day OHLCV history and computes RSI, ADX, EMA-20/50/200, ATR, 3M relative strength vs Nifty',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
    {
      id: 'fundamental_scan', name: 'Fundamentals Analyst',
      agentName: 'Fundamentals Analyst',
      agentRole: 'Scrapes Screener.in for quarterly profit trends, ROE, and D/E ratios',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
    {
      id: 'sector_check', name: 'Sector Monitor',
      agentName: 'Sector Monitor',
      agentRole: 'Measures 5-day sector index performance to identify sector-level headwinds',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
    {
      id: 'sell_scoring', name: 'Sell Signal Engine',
      agentName: 'Sell Signal Engine',
      agentRole: 'Multi-factor sell urgency scoring with AI exit reasoning and news analysis',
      status: 'pending', stocksRemaining: null, previousCount: null,
      startedAt: null, completedAt: null, durationMs: null, logs: [],
    },
  ];

  // Pipeline mode: 'buy' (default) or 'sell'
  pipelineMode: 'buy' | 'sell' = 'buy';

  activityLog: LogEntry[] = [];
  selectedStocks: StockResult[] = [];
  sellResults: SellResult[] = [];
  isRunning = false;
  isCompleted = false;
  pipelineMessage = '';
  startedAt = '';
  completedAt = '';
  sellPipelineMessage = '';
  sellStartedAt = '';
  sellCompletedAt = '';
  sellSummary: { strong_sell_count: number; sell_count: number; watch_count: number; hold_count: number } | null = null;

  // Strategy gear slider
  selectedGear = 3;
  readonly GEAR_INFO: Record<number, GearInfo> = {
    1: { label: 'Fortress', description: 'Maximum safety — large caps, deep dips only, strict fundamentals.' },
    2: { label: 'Cautious', description: 'Conservative picks — large caps with standard checks.' },
    3: { label: 'Balanced', description: 'Default strategy — broad universe, moderate filters.' },
    4: { label: 'Growth', description: 'Capital appreciation — shallow dips, relaxed fundamentals.' },
    5: { label: 'Turbo', description: 'Momentum plays — small caps, breakouts, no fundamental filter.' },
  };
  readonly GEAR_ICONS: Record<number, string> = {
    1: '\u{1F6E1}\uFE0F', // shield
    2: '\u{1F9F1}',       // brick
    3: '\u2696\uFE0F',    // scale
    4: '\u{1F680}',       // rocket
    5: '\u{1F525}',       // fire
  };

  private readonly GEAR_COLORS: Record<number, string> = {
    1: '#22c55e', // green — fortress
    2: '#2dd4bf', // teal — cautious
    3: '#3b82f6', // blue — balanced
    4: '#f97316', // orange — growth
    5: '#ef4444', // red — turbo
  };

  getSliderColor(): string {
    return this.GEAR_COLORS[this.selectedGear] ?? this.GEAR_COLORS[3];
  }

  // LLM provider selector
  selectedProvider: 'gemini' | 'claude' | 'openai' = 'gemini';
  readonly PROVIDER_INFO: Record<string, { label: string; badge: string; description: string }> = {
    gemini: { label: 'Gemini', badge: 'Default', description: 'Gemini 2.5 Flash — fast, cost-effective' },
    claude: { label: 'Claude', badge: 'Deep Think', description: 'Claude Sonnet 4.6 — extended thinking, richer risk analysis' },
    openai: { label: 'GPT-4o', badge: 'Fallback', description: 'GPT-4o Mini — broad knowledge base' },
  };

  // Pipeline result metadata
  atrStopLossMultiplier = 1.5;
  marketRegime: MarketRegime | null = null;

  // Trade modal state
  showTradeModal = false;
  tradeDetails: TradeDetails | null = null;
  isLoadingTrade = false;
  tradeError = '';
  availableFunds: number | null = null;

  // Simulator / live trading state
  simulatorState: SimulatorState | null = null;
  isExiting: { [tradeId: string]: boolean } = {};
  showHistory = false;
  tradeConfirmLoading = false;

  // Trading mode
  tradingMode: 'simulator' | 'live' = 'simulator';
  showModeConfirmDialog = false;
  liveConfirmPhrase = '';
  readonly LIVE_CONFIRM_PHRASE = 'I understand this uses real money';

  // Staging list
  stagingList: StockResult[] = [];

  // Bulk trade modal state
  showBulkTradeModal = false;
  bulkTradeLoading = false;
  bulkTradeExecuting = false;
  bulkTradeProgress: number | null = null;
  bulkTradeDetails: {
    availableFunds: number;
    perStockAllocation: number;
    stocks: Array<{
      symbol: string;
      ltp: number;
      quantity: number;
      atr: number;
      status: 'pending' | 'success' | 'error';
      instrument_token?: number;
    }>;
  } | null = null;

  // Expanded stock card tracking
  expandedStock: string | null = null;

  // Agent execution logs panel
  showAgentLogs = false;
  expandedLogStep: string | null = null;

  // Market data
  nifty: MarketIndex | null = null;
  sensex: MarketIndex | null = null;
  marketGainers: Stock[] = [];
  marketLosers: Stock[] = [];
  isMarketLoading = false;
  marketError = '';

  // Automation panel state
  automationStatus: AutomationStatus | null = null;
  automationEnabled = false;
  automationMode: 'simulator' | 'live' = 'simulator';
  automationRunning = false;
  automationRunResult: AutomationRunRecord | null = null;
  automationDryRun = true;

  // Panel tab state
  leftTab: 'setup' | 'results' = 'setup';
  rightTab: 'staging' | 'history' | 'automation' = 'staging';

  private abortController: AbortController | null = null;
  private simulatorSub: Subscription | null = null;
  private marketRefreshSub: Subscription | null = null;
  private automationRefreshSub: Subscription | null = null;

  constructor(
    private router: Router,
    private ngZone: NgZone,
    private kiteService: KiteService,
    private simulatorService: SimulatorService,
    private demoService: DemoService
  ) {}

  private static readonly RESULTS_STORAGE_KEY = 'cognicap_pipeline_results';
  private static readonly SELL_RESULTS_STORAGE_KEY = 'cognicap_sell_results';

  get activePipelineSteps(): PipelineStep[] {
    return this.pipelineMode === 'sell' ? this.sellPipelineSteps : this.pipelineSteps;
  }

  ngOnInit(): void {
    this.loadSavedResults();
    this.loadSavedSellResults();
    this.loadMarketData();
    this.loadAutomationStatus();
    this.simulatorService.startPolling(1000);
    this.simulatorSub = this.simulatorService.state$.subscribe(state => {
      if (state) {
        this.simulatorState = state;
      }
    });
    this.simulatorService.tradingMode$.subscribe(mode => {
      this.tradingMode = mode;
    });
    // Refresh market data every 30s
    this.marketRefreshSub = interval(30000).subscribe(() => this.loadMarketData());
    // Refresh automation status every 60s
    this.automationRefreshSub = interval(60000).subscribe(() => this.loadAutomationStatus());
  }

  ngOnDestroy(): void {
    this.cancelPipeline();
    this.simulatorService.stopPolling();
    this.simulatorSub?.unsubscribe();
    this.marketRefreshSub?.unsubscribe();
    this.automationRefreshSub?.unsubscribe();
  }

  private loadMarketData(): void {
    this.isMarketLoading = true;
    forkJoin({
      indices: this.kiteService.getMarketIndices(),
      stocks: this.kiteService.getTopStocks()
    }).subscribe({
      next: (results) => {
        if (results.indices.success) {
          this.nifty = results.indices.nifty || null;
          this.sensex = results.indices.sensex || null;
        }
        if (results.stocks.success) {
          this.marketGainers = results.stocks.top_gainers || [];
          this.marketLosers = results.stocks.top_losers || [];
        }
        this.isMarketLoading = false;
      },
      error: () => {
        this.isMarketLoading = false;
      }
    });
  }

  goBack(): void {
    this.router.navigate(['/dashboard']);
  }

  goToLogin(): void {
    localStorage.removeItem('access_token');
    this.router.navigate(['/login']);
  }

  async startPipeline(): Promise<void> {
    if (this.demoService.isDemo) { this.demoService.showKitePrompt(); return; }
    // Reset state
    this.leftTab = 'setup';
    this.isRunning = true;
    this.isCompleted = false;
    this.activityLog = [];
    this.selectedStocks = [];
    this.pipelineMessage = '';
    this.pipelineSteps.forEach(s => {
      s.status = 'pending';
      s.stocksRemaining = null;
      s.previousCount = null;
      s.startedAt = null;
      s.completedAt = null;
      s.durationMs = null;
      s.logs = [];
    });
    this.showAgentLogs = false;
    this.expandedLogStep = null;
    this.abortController = new AbortController();

    const accessToken = localStorage.getItem('access_token') || '';

    try {
      const response = await fetch('http://localhost:5000/api/decision-support/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_token: accessToken,
          config: {
            gear: this.selectedGear,
            llm_provider: this.selectedProvider,
          },
        }),
        signal: this.abortController.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`Request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEventType = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          if (buffer.trim()) {
            this.processLines(buffer.split('\n'), currentEventType);
          }
          break;
        }

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
            } catch {
              // skip malformed data
            }
            currentEventType = '';
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        this.addLog('pipeline', 'Pipeline cancelled by user.', 'info');
      } else {
        this.addLog('pipeline', `Pipeline error: ${err.message}`, 'error');
      }
    } finally {
      this.ngZone.run(() => {
        this.isRunning = false;
        if (!this.isCompleted) {
          this.isCompleted = true;
        }
      });
    }
  }

  private processLines(lines: string[], currentEventType: string): void {
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEventType = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEventType) {
        try {
          const data = JSON.parse(line.slice(6));
          this.ngZone.run(() => this.handleEvent(currentEventType, data));
        } catch {
          // skip
        }
        currentEventType = '';
      }
    }
  }

  cancelPipeline(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }

  private handleEvent(event: string, data: any): void {
    switch (event) {
      case 'step_start':
        if (data.step && data.step !== 'pipeline') {
          this.updateStepStatus(data.step, 'running');
          const step = this.pipelineSteps.find(s => s.id === data.step);
          if (step) {
            step.startedAt = new Date();
            // Update agent metadata from backend if provided
            if (data.agent_name) step.agentName = data.agent_name;
            if (data.agent_role) step.agentRole = data.agent_role;
          }
        }
        this.addLog(data.step || 'pipeline', data.description || 'Starting...', 'info');
        break;

      case 'step_log':
        this.addLog(data.step || 'pipeline', data.message, 'info');
        break;

      case 'step_complete': {
        this.updateStepStatus(data.step, 'completed');
        const step = this.pipelineSteps.find(s => s.id === data.step);
        if (step) {
          step.stocksRemaining = data.stocks_remaining;
          step.completedAt = new Date();
          step.durationMs = data.duration_ms ?? (step.startedAt ? Date.now() - step.startedAt.getTime() : null);
          // For universe_filter, set its own previousCount from initial_count
          if (data.initial_count && step.id === 'universe_filter') {
            step.previousCount = data.initial_count;
          }
          // Set previousCount for the next step
          const idx = this.pipelineSteps.indexOf(step);
          if (idx < this.pipelineSteps.length - 1) {
            this.pipelineSteps[idx + 1].previousCount = data.stocks_remaining;
          }
        }
        const passMsg = `${data.stocks_remaining} stock${data.stocks_remaining === 1 ? '' : 's'} passed`;
        this.addLog(data.step, passMsg, 'success');
        break;
      }

      case 'final_result':
        this.selectedStocks = data.stocks || [];
        this.pipelineMessage = data.message || '';
        this.startedAt = data.started_at || '';
        this.completedAt = data.completed_at || '';
        this.atrStopLossMultiplier = data.atr_stop_loss_multiplier || 1.5;
        this.marketRegime = data.market_regime || null;
        this.isCompleted = true;
        this.leftTab = 'results';
        this.addLog('pipeline', data.message || 'Pipeline complete.', 'success');
        this.saveResults();
        break;

      case 'error':
        this.updateStepStatus(data.step, 'error');
        this.addLog(data.step || 'pipeline', data.message, 'error');
        break;

      case 'end':
        // Stream ended
        break;
    }
  }

  private updateStepStatus(stepId: string, status: 'running' | 'completed' | 'error'): void {
    const step = this.pipelineSteps.find(s => s.id === stepId);
    if (step) {
      step.status = status;
    }
  }

  private addLog(step: string, message: string, type: 'info' | 'success' | 'error'): void {
    const entry: LogEntry = { timestamp: new Date(), step, message, type };
    this.activityLog.push(entry);
    // Also store in the step's own log list
    const pipelineStep = this.pipelineSteps.find(s => s.id === step);
    if (pipelineStep) {
      pipelineStep.logs.push(entry);
    }
  }

  toggleAgentLogs(): void {
    this.showAgentLogs = !this.showAgentLogs;
    if (this.showAgentLogs && !this.expandedLogStep) {
      // Auto-expand the last completed step
      const lastDone = [...this.pipelineSteps].reverse().find(s => s.status === 'completed' || s.status === 'running');
      this.expandedLogStep = lastDone?.id ?? null;
    }
  }

  toggleLogStep(stepId: string): void {
    this.expandedLogStep = this.expandedLogStep === stepId ? null : stepId;
  }

  formatDuration(ms: number | null): string {
    if (ms === null) return '';
    if (ms < 1000) return `${ms}ms`;
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    if (m > 0) return `${m}m ${s % 60}s`;
    return `${s}s`;
  }

  private saveResults(): void {
    const payload = {
      selectedStocks: this.selectedStocks,
      pipelineMessage: this.pipelineMessage,
      startedAt: this.startedAt,
      completedAt: this.completedAt,
      atrStopLossMultiplier: this.atrStopLossMultiplier,
      marketRegime: this.marketRegime,
      pipelineSteps: this.pipelineSteps.map(s => ({
        id: s.id,
        status: s.status,
        stocksRemaining: s.stocksRemaining,
        previousCount: s.previousCount,
        durationMs: s.durationMs,
        logs: s.logs.map(l => ({ ...l, timestamp: l.timestamp.toISOString() })),
      })),
    };
    localStorage.setItem(TradingAgentComponent.RESULTS_STORAGE_KEY, JSON.stringify(payload));
  }

  private loadSavedResults(): void {
    const raw = localStorage.getItem(TradingAgentComponent.RESULTS_STORAGE_KEY);
    if (!raw) return;
    try {
      const saved = JSON.parse(raw);
      this.selectedStocks = saved.selectedStocks || [];
      this.pipelineMessage = saved.pipelineMessage || '';
      this.startedAt = saved.startedAt || '';
      this.completedAt = saved.completedAt || '';
      this.atrStopLossMultiplier = saved.atrStopLossMultiplier || 1.5;
      this.marketRegime = saved.marketRegime || null;
      if (this.selectedStocks.length > 0 || this.pipelineMessage) {
        this.isCompleted = true;
        this.leftTab = 'results';
      }
      if (saved.pipelineSteps) {
        for (const saved_step of saved.pipelineSteps) {
          const step = this.pipelineSteps.find(s => s.id === saved_step.id);
          if (step) {
            step.status = saved_step.status;
            step.stocksRemaining = saved_step.stocksRemaining;
            step.previousCount = saved_step.previousCount;
            step.durationMs = saved_step.durationMs ?? null;
            step.logs = (saved_step.logs || []).map((l: any) => ({
              ...l, timestamp: new Date(l.timestamp),
            }));
          }
        }
      }
    } catch {
      // Corrupted data, ignore
    }
  }

  openTradeModal(stock: StockResult): void {
    this.showTradeModal = true;
    this.isLoadingTrade = true;
    this.tradeDetails = null;
    this.tradeError = '';

    const totalStocks = this.filteredStocks.length;

    // In simulator mode, use the simulator balance; otherwise fetch from Kite
    const funds$ = this.simulatorState
      ? of({ success: true, available_funds: this.simulatorState.account_summary.current_balance } as any)
      : this.kiteService.getAvailableFunds();

    forkJoin({
      funds: funds$,
      exits: this.kiteService.calculateExits(stock.symbol, stock.instrument_token, stock.current_price)
    }).subscribe({
      next: ({ funds, exits }: { funds: any; exits: any }) => {
        if (!funds.success) {
          this.tradeError = funds.error || 'Failed to fetch available funds';
          this.isLoadingTrade = false;
          return;
        }
        if (!exits.success) {
          this.tradeError = exits.error || 'Failed to calculate exit levels';
          this.isLoadingTrade = false;
          return;
        }

        const availableFunds = funds.available_funds!;
        const investmentAmount = availableFunds / totalStocks;
        // Use live LTP from calculate-exits (not stale pipeline price).
        // Mirror the backend's entry price formula (LTP × 1.0005 spread)
        // so quantity × entryPrice never exceeds investmentAmount.
        const liveLtp = exits.ltp!;
        const entryPriceEst = liveLtp * 1.0005;
        const quantity = Math.floor(investmentAmount / entryPriceEst);

        this.availableFunds = availableFunds;
        this.tradeDetails = {
          symbol: stock.symbol,
          ltp: liveLtp,
          atr: exits.atr!,
          initialSl: exits.initial_sl!,
          trailMultiplier: this.atrStopLossMultiplier,
          riskPerShare: exits.risk_per_share!,
          availableFunds,
          investmentAmount: Math.round(investmentAmount * 100) / 100,
          quantity,
          totalStocks,
        };
        this.isLoadingTrade = false;
      },
      error: (err) => {
        this.tradeError = err?.error?.error || 'Could not connect to server. Is the backend running?';
        this.isLoadingTrade = false;
      }
    });
  }

  closeTradeModal(): void {
    this.showTradeModal = false;
    this.tradeDetails = null;
    this.isLoadingTrade = false;
    this.tradeError = '';
  }

  // --- Trading mode toggle ---

  requestSwitchToLive(): void {
    this.showModeConfirmDialog = true;
    this.liveConfirmPhrase = '';
  }

  cancelModeSwitch(): void {
    this.showModeConfirmDialog = false;
    this.liveConfirmPhrase = '';
  }

  confirmSwitchToLive(): void {
    if (this.liveConfirmPhrase !== this.LIVE_CONFIRM_PHRASE) return;
    this.simulatorService.setTradingMode('live', true).subscribe({
      next: () => {
        this.showModeConfirmDialog = false;
        this.liveConfirmPhrase = '';
        this.addLog('trading', 'Switched to LIVE trading mode — real money will be used', 'info');
      },
      error: (err) => {
        this.addLog('trading', `Failed to switch mode: ${err?.error?.error || err.message}`, 'error');
      }
    });
  }

  switchToSimulator(): void {
    this.simulatorService.setTradingMode('simulator', true).subscribe({
      next: () => {
        this.addLog('trading', 'Switched to simulator mode', 'info');
      },
      error: () => {}
    });
  }

  confirmTrade(): void {
    if (!this.tradeDetails || this.tradeConfirmLoading) return;

    // Double-confirmation for live mode
    if (this.tradingMode === 'live') {
      const confirmed = window.confirm(
        `LIVE TRADING WARNING\n\n` +
        `You are about to place a REAL order:\n` +
        `${this.tradeDetails.quantity} shares of ${this.tradeDetails.symbol} ` +
        `@ ₹${this.tradeDetails.ltp.toLocaleString('en-IN')}\n\n` +
        `Total value: ₹${(this.tradeDetails.ltp * this.tradeDetails.quantity).toLocaleString('en-IN')}\n\n` +
        `This will use REAL MONEY. Continue?`
      );
      if (!confirmed) return;
    }

    this.tradeConfirmLoading = true;

    const stock = this.selectedStocks.find(s => s.symbol === this.tradeDetails!.symbol);
    this.simulatorService.executeOrder(
      this.tradeDetails.symbol,
      this.tradeDetails.quantity,
      this.tradeDetails.atr,
      this.tradeDetails.trailMultiplier,
      stock?.instrument_token,
      this.tradeDetails.ltp
    ).subscribe({
      next: (result) => {
        this.tradeConfirmLoading = false;
        if (result.success) {
          const modeLabel = this.tradingMode === 'live' ? 'LIVE trade' : 'Virtual trade';
          this.addLog('trading', result.message || `${modeLabel} executed`, 'success');
          this.closeTradeModal();
        } else {
          this.tradeError = result.error || 'Trade failed';
        }
      },
      error: (err) => {
        this.tradeConfirmLoading = false;
        this.tradeError = err?.error?.error || 'Could not execute trade. Is the backend running?';
      }
    });
  }

  exitPosition(tradeId: string): void {
    this.isExiting[tradeId] = true;
    this.simulatorService.closePosition(tradeId).subscribe({
      next: (result) => {
        this.isExiting[tradeId] = false;
        if (result.success) {
          this.addLog('simulator', result.message || 'Position closed', 'success');
        }
      },
      error: () => {
        this.isExiting[tradeId] = false;
      }
    });
  }

  togglePipelineMode(mode: 'buy' | 'sell'): void {
    if (this.isRunning || this.pipelineMode === mode) return;
    this.pipelineMode = mode;
    this.isCompleted = false;
    this.expandedStock = null;
    this.leftTab = 'setup';

    // Restore previously completed results for the new mode
    if (mode === 'buy' && (this.selectedStocks.length > 0 || this.pipelineMessage)) {
      this.isCompleted = true;
      this.leftTab = 'results';
    } else if (mode === 'sell' && (this.sellResults.length > 0 || this.sellPipelineMessage)) {
      this.isCompleted = true;
      this.leftTab = 'results';
    }
  }

  async startSellPipeline(): Promise<void> {
    if (this.demoService.isDemo) { this.demoService.showKitePrompt(); return; }
    this.leftTab = 'setup';
    this.isRunning = true;
    this.isCompleted = false;
    this.sellResults = [];
    this.sellPipelineMessage = '';
    this.sellSummary = null;
    this.activityLog = [];

    this.sellPipelineSteps.forEach(s => {
      s.status = 'pending';
      s.stocksRemaining = null;
      s.previousCount = null;
      s.startedAt = null;
      s.completedAt = null;
      s.durationMs = null;
      s.logs = [];
    });
    this.showAgentLogs = false;
    this.expandedLogStep = null;
    this.abortController = new AbortController();

    const accessToken = localStorage.getItem('access_token') || '';

    try {
      const response = await fetch('http://localhost:5000/api/decision-support/sell', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_token: accessToken,
          config: { llm_provider: this.selectedProvider },
        }),
        signal: this.abortController.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`Request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEventType = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          if (buffer.trim()) {
            this.processSellLines(buffer.split('\n'), currentEventType);
          }
          break;
        }
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
              this.ngZone.run(() => this.handleSellEvent(evt, data));
            } catch {
              // skip malformed data
            }
            currentEventType = '';
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        this.addLog('pipeline', 'Sell analysis cancelled by user.', 'info');
      } else {
        this.addLog('pipeline', `Sell analysis error: ${err.message}`, 'error');
      }
    } finally {
      this.ngZone.run(() => {
        this.isRunning = false;
        if (!this.isCompleted) {
          this.isCompleted = true;
        }
      });
    }
  }

  private processSellLines(lines: string[], currentEventType: string): void {
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEventType = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEventType) {
        try {
          const data = JSON.parse(line.slice(6));
          this.ngZone.run(() => this.handleSellEvent(currentEventType, data));
        } catch {
          // skip
        }
        currentEventType = '';
      }
    }
  }

  private handleSellEvent(event: string, data: any): void {
    switch (event) {
      case 'step_start':
        if (data.step && data.step !== 'pipeline') {
          const step = this.sellPipelineSteps.find(s => s.id === data.step);
          if (step) {
            step.status = 'running';
            step.startedAt = new Date();
            if (data.agent_name) step.agentName = data.agent_name;
            if (data.agent_role) step.agentRole = data.agent_role;
          }
        }
        this.addSellLog(data.step || 'pipeline', data.description || 'Starting...', 'info');
        break;

      case 'step_log':
        this.addSellLog(data.step || 'pipeline', data.message, 'info');
        break;

      case 'step_complete': {
        const step = this.sellPipelineSteps.find(s => s.id === data.step);
        if (step) {
          step.status = 'completed';
          step.stocksRemaining = data.holdings_count ?? data.stocks_remaining ?? null;
          step.completedAt = new Date();
          step.durationMs = data.duration_ms ?? (step.startedAt ? Date.now() - step.startedAt.getTime() : null);
        }
        const count = data.holdings_count ?? data.stocks_remaining ?? 0;
        this.addSellLog(data.step, `${count} holding${count === 1 ? '' : 's'} processed`, 'success');
        break;
      }

      case 'final_result':
        this.sellResults = data.holdings || [];
        this.sellPipelineMessage = data.message || '';
        this.sellStartedAt = data.started_at || '';
        this.sellCompletedAt = data.completed_at || '';
        this.marketRegime = data.market_regime || null;
        this.sellSummary = {
          strong_sell_count: data.strong_sell_count || 0,
          sell_count: data.sell_count || 0,
          watch_count: data.watch_count || 0,
          hold_count: data.hold_count || 0,
        };
        this.isCompleted = true;
        this.leftTab = 'results';
        this.addSellLog('pipeline', data.message || 'Sell analysis complete.', 'success');
        this.saveSellResults();
        break;

      case 'error':
        const errStep = this.sellPipelineSteps.find(s => s.id === data.step);
        if (errStep) errStep.status = 'error';
        this.addSellLog(data.step || 'pipeline', data.message, 'error');
        break;

      case 'end':
        break;
    }
  }

  private addSellLog(step: string, message: string, type: 'info' | 'success' | 'error'): void {
    const entry: LogEntry = { timestamp: new Date(), step, message, type };
    this.activityLog.push(entry);
    const pipelineStep = this.sellPipelineSteps.find(s => s.id === step);
    if (pipelineStep) {
      pipelineStep.logs.push(entry);
    }
  }

  private saveSellResults(): void {
    const payload = {
      sellResults: this.sellResults,
      sellPipelineMessage: this.sellPipelineMessage,
      sellStartedAt: this.sellStartedAt,
      sellCompletedAt: this.sellCompletedAt,
      sellSummary: this.sellSummary,
      marketRegime: this.marketRegime,
      sellPipelineSteps: this.sellPipelineSteps.map(s => ({
        id: s.id,
        status: s.status,
        stocksRemaining: s.stocksRemaining,
        durationMs: s.durationMs,
        logs: s.logs.map(l => ({ ...l, timestamp: l.timestamp.toISOString() })),
      })),
    };
    localStorage.setItem(TradingAgentComponent.SELL_RESULTS_STORAGE_KEY, JSON.stringify(payload));
  }

  private loadSavedSellResults(): void {
    const raw = localStorage.getItem(TradingAgentComponent.SELL_RESULTS_STORAGE_KEY);
    if (!raw) return;
    try {
      const saved = JSON.parse(raw);
      this.sellResults = saved.sellResults || [];
      this.sellPipelineMessage = saved.sellPipelineMessage || '';
      this.sellStartedAt = saved.sellStartedAt || '';
      this.sellCompletedAt = saved.sellCompletedAt || '';
      this.sellSummary = saved.sellSummary || null;
      if (saved.sellPipelineSteps) {
        for (const saved_step of saved.sellPipelineSteps) {
          const step = this.sellPipelineSteps.find(s => s.id === saved_step.id);
          if (step) {
            step.status = saved_step.status;
            step.stocksRemaining = saved_step.stocksRemaining;
            step.durationMs = saved_step.durationMs ?? null;
            step.logs = (saved_step.logs || []).map((l: any) => ({ ...l, timestamp: new Date(l.timestamp) }));
          }
        }
      }
    } catch {
      // Corrupted data, ignore
    }
  }

  // Sell mode helpers
  getSellUrgencyClass(score: number): string {
    if (score >= 70) return 'urgency-strong-sell';
    if (score >= 40) return 'urgency-sell';
    if (score >= 20) return 'urgency-watch';
    return 'urgency-hold';
  }

  getSellUrgencyColor(score: number): string {
    if (score >= 70) return '#ef4444';
    if (score >= 40) return '#f97316';
    if (score >= 20) return '#eab308';
    return '#6b7280';
  }

  canExitSellPosition(symbol: string): boolean {
    if (!this.simulatorState) return false;
    return this.simulatorState.positions.some(p => p.symbol === symbol);
  }

  exitSellPosition(symbol: string): void {
    if (!this.simulatorState) return;
    const position = this.simulatorState.positions.find(p => p.symbol === symbol);
    if (!position) return;
    this.exitPosition(position.trade_id);
  }

  getStepIconForMode(step: PipelineStep): string {
    const steps = this.activePipelineSteps;
    switch (step.status) {
      case 'completed': return '\u2713';
      case 'error': return '\u2717';
      case 'running': return '\u25CF';
      default: return String(steps.indexOf(step) + 1);
    }
  }

  switchToTradeMode(): void {
    // Placeholder — live trade mode not yet implemented
    console.log('Trade mode coming soon');
  }

  resetSimulator(): void {
    this.simulatorService.resetSimulator().subscribe({
      next: () => {
        this.addLog('simulator', 'Simulator reset to ₹1,00,000', 'info');
      }
    });
  }

  // ── Staging list ────────────────────────────────────────────

  isInStaging(stock: StockResult): boolean {
    return this.stagingList.some(s => s.symbol === stock.symbol);
  }

  toggleStaging(stock: StockResult): void {
    if (this.isInStaging(stock)) {
      this.stagingList = this.stagingList.filter(s => s.symbol !== stock.symbol);
    } else {
      this.stagingList = [...this.stagingList, stock];
    }
  }

  removeFromStaging(stock: StockResult): void {
    this.stagingList = this.stagingList.filter(s => s.symbol !== stock.symbol);
  }

  clearStaging(): void {
    this.stagingList = [];
  }

  openBulkTradeModal(): void {
    if (this.stagingList.length === 0) return;
    this.showBulkTradeModal = true;
    this.bulkTradeLoading = true;
    this.bulkTradeDetails = null;
    this.bulkTradeProgress = null;
    this.bulkTradeExecuting = false;

    const availableFunds = this.simulatorState?.account_summary.current_balance ?? 0;
    const perStockAllocation = availableFunds / this.stagingList.length;

    const exitRequests = this.stagingList.map(stock =>
      this.kiteService.calculateExits(stock.symbol, stock.instrument_token, stock.current_price)
    );

    forkJoin(exitRequests).subscribe({
      next: (results) => {
        const stocks = this.stagingList.map((stock, i) => {
          const exits = results[i];
          const ltp = exits.success ? exits.ltp! : stock.current_price;
          const entryPriceEst = ltp * 1.0005;
          const quantity = Math.floor(perStockAllocation / entryPriceEst);
          return {
            symbol: stock.symbol,
            ltp,
            quantity,
            atr: exits.atr ?? 0,
            status: 'pending' as const,
            instrument_token: stock.instrument_token,
          };
        });
        this.bulkTradeDetails = { availableFunds, perStockAllocation, stocks };
        this.bulkTradeLoading = false;
      },
      error: () => {
        this.bulkTradeLoading = false;
        this.showBulkTradeModal = false;
      }
    });
  }

  closeBulkTradeModal(): void {
    if (this.bulkTradeExecuting) return;
    this.showBulkTradeModal = false;
    this.bulkTradeDetails = null;
    this.bulkTradeProgress = null;
  }

  async confirmBulkTrade(): Promise<void> {
    if (!this.bulkTradeDetails || this.bulkTradeExecuting) return;
    this.bulkTradeExecuting = true;
    this.bulkTradeProgress = 0;

    for (const item of this.bulkTradeDetails.stocks) {
      try {
        const result = await this.simulatorService.executeOrder(
          item.symbol,
          item.quantity,
          item.atr,
          this.atrStopLossMultiplier,
          item.instrument_token,
          item.ltp
        ).toPromise();
        item.status = result?.success ? 'success' : 'error';
        this.addLog('simulator', result?.message || `Trade ${item.symbol}`, result?.success ? 'success' : 'error');
      } catch {
        item.status = 'error';
      }
      this.bulkTradeProgress!++;
    }

    this.bulkTradeExecuting = false;
    const successSymbols = new Set(
      this.bulkTradeDetails.stocks.filter(s => s.status === 'success').map(s => s.symbol)
    );
    if (successSymbols.size > 0) {
      this.stagingList = this.stagingList.filter(s => !successSymbols.has(s.symbol));
      this.addLog('simulator', `${successSymbols.size} virtual trade(s) executed`, 'success');
    }

    setTimeout(() => this.closeBulkTradeModal(), 1800);
  }

  getConvictionColor(score: number): string {
    if (score >= 5) return '#22c55e';
    if (score >= 4) return '#22c55e';
    if (score >= 3) return '#3b82f6';
    if (score >= 2) return '#f97316';
    return '#ef4444';
  }

  getCompositeScoreColor(score: number): string {
    if (score >= 70) return 'rgba(34, 197, 94, 0.2)';
    if (score >= 50) return 'rgba(59, 130, 246, 0.2)';
    if (score >= 30) return 'rgba(249, 115, 22, 0.2)';
    return 'rgba(239, 68, 68, 0.2)';
  }

  getCompositeScoreTextColor(score: number): string {
    if (score >= 70) return '#22c55e';
    if (score >= 50) return '#3b82f6';
    if (score >= 30) return '#f97316';
    return '#ef4444';
  }

  toggleHistory(): void {
    this.showHistory = !this.showHistory;
  }

  toggleStockCard(symbol: string): void {
    this.expandedStock = this.expandedStock === symbol ? null : symbol;
  }

  getStepIcon(step: PipelineStep): string {
    switch (step.status) {
      case 'completed': return '\u2713';
      case 'error': return '\u2717';
      case 'running': return '\u25CF';
      default: return String(this.activePipelineSteps.indexOf(step) + 1);
    }
  }

  formatTime(date: Date): string {
    return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(value);
  }

  formatNumber(value: number): string {
    if (value >= 1_000_000) {
      return (value / 1_000_000).toFixed(1) + 'M';
    }
    if (value >= 1_000) {
      return (value / 1_000).toFixed(0) + 'K';
    }
    return value.toLocaleString('en-IN');
  }

  get filteredStocks(): StockResult[] {
    if (!this.simulatorState || this.simulatorState.positions.length === 0) {
      return this.selectedStocks;
    }
    const activeSymbols = new Set(this.simulatorState.positions.map(p => p.symbol));
    return this.selectedStocks.filter(s => !activeSymbols.has(s.symbol));
  }

  getUnrealizedPnl(pos: SimulatorPosition): number {
    const ltp = parseFloat(String(pos.ltp || pos.entry_price));
    const entry = parseFloat(String(pos.entry_price));
    const qty = parseInt(String(pos.quantity), 10);
    return Math.round((ltp - entry) * qty * 100) / 100;
  }

  isBreakingOut(pos: SimulatorPosition): boolean {
    const ltp = Number(pos.ltp || pos.entry_price);
    const high = Number(pos.highest_price_seen || pos.entry_price);
    return ltp >= high;
  }

  getTrailStatus(position: SimulatorPosition): { icon: string; label: string; cssClass: string } {
    const status = this.simulatorService.computeTrailStatus(position);
    switch (status) {
      case 'RUNAWAY':
        return { icon: '\u{1F7E2}', label: 'Runaway', cssClass: 'runaway' };
      case 'HOLDING':
        return { icon: '\u{1F7E1}', label: 'Holding', cssClass: 'holding' };
      case 'CRITICAL':
        return { icon: '\u{1F534}', label: 'Critical', cssClass: 'critical' };
      case 'STALLED':
        return { icon: '\u26AA', label: 'Stalled', cssClass: 'stalled' };
    }
  }

  // ── Automation panel ────────────────────────────────────────────────────

  loadAutomationStatus(): void {
    this.simulatorService.getAutomationStatus().subscribe({
      next: (status) => {
        this.automationStatus = status;
        this.automationEnabled = status.enabled;
        this.automationMode = status.mode;
      },
      error: () => {}
    });
  }

  toggleAutomation(): void {
    // automationEnabled is already updated by [(ngModel)] before (change) fires
    this.simulatorService.enableAutomation(this.automationEnabled, this.automationMode).subscribe({
      next: (res) => {
        this.automationEnabled = res.enabled;
        this.loadAutomationStatus();
      },
      error: () => {}
    });
  }

  setAutomationMode(mode: 'simulator' | 'live'): void {
    this.automationMode = mode;
    this.simulatorService.enableAutomation(this.automationEnabled, mode).subscribe({
      next: () => this.loadAutomationStatus(),
      error: () => {}
    });
  }

  runAutomationNow(): void {
    if (this.automationRunning) return;
    this.automationRunning = true;
    this.automationRunResult = null;
    const token = localStorage.getItem('access_token') || '';
    this.simulatorService.runAutomationNow(token, this.automationDryRun).subscribe({
      next: (result) => {
        this.automationRunning = false;
        this.automationRunResult = result;
        this.loadAutomationStatus();
      },
      error: (err) => {
        this.automationRunning = false;
        console.error('[Automation] run-now failed', err);
      }
    });
  }

  formatNextRun(isoString: string | null | undefined): string {
    if (!isoString) return 'Not scheduled';
    const d = new Date(isoString);
    return d.toLocaleDateString('en-IN', {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
      timeZone: 'Asia/Kolkata'
    });
  }

  getGearLabel(gear: number): string {
    return this.GEAR_INFO[gear]?.label ?? `Gear ${gear}`;
  }
}
