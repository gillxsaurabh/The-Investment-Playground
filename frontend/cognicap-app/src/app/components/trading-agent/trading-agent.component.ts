import { Component, OnDestroy, OnInit, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { KiteService, MarketIndex, Stock } from '../../services/kite.service';
import { SimulatorService, SimulatorState, SimulatorPosition, SimulatorTradeHistory, SectorEntry } from '../../services/simulator.service';
import { HeaderBannerComponent } from '../shared/header-banner/header-banner.component';
import { forkJoin, of, interval, Subscription } from 'rxjs';
import { PositionsChartComponent } from './positions-chart.component';

interface PipelineStep {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  stocksRemaining: number | null;
  previousCount: number | null;
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
  sector_daily_change: number;
  why_selected: string;
  ema_20: number;
  ema_200: number;
  stock_3m_return: number;
  nifty_3m_return: number;
  avg_volume_20d: number;
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
    { id: 'universe_filter', name: 'Get Top Stocks', status: 'pending', stocksRemaining: null, previousCount: null },
    { id: 'technical_setup', name: 'Apply Technical Rules', status: 'pending', stocksRemaining: null, previousCount: null },
    { id: 'fundamentals', name: 'Check Company Health', status: 'pending', stocksRemaining: null, previousCount: null },
    { id: 'sector_health', name: 'Vibe Check', status: 'pending', stocksRemaining: null, previousCount: null },
  ];

  activityLog: LogEntry[] = [];
  selectedStocks: StockResult[] = [];
  isRunning = false;
  isCompleted = false;
  pipelineMessage = '';
  startedAt = '';
  completedAt = '';

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

  // Pipeline result metadata
  atrStopLossMultiplier = 1.5;

  // Trade modal state
  showTradeModal = false;
  tradeDetails: TradeDetails | null = null;
  isLoadingTrade = false;
  tradeError = '';
  availableFunds: number | null = null;

  // Simulator state
  simulatorState: SimulatorState | null = null;
  isExiting: { [tradeId: string]: boolean } = {};
  showHistory = false;
  tradeConfirmLoading = false;

  // Sector leaderboard
  sectorLeaderboard: SectorEntry[] = [];
  isSectorResearching = false;
  sectorResearchedAt = '';

  // Expanded stock card tracking
  expandedStock: string | null = null;

  // Market data
  nifty: MarketIndex | null = null;
  sensex: MarketIndex | null = null;
  marketGainers: Stock[] = [];
  marketLosers: Stock[] = [];
  isMarketLoading = false;
  marketError = '';

  private abortController: AbortController | null = null;
  private simulatorSub: Subscription | null = null;
  private marketRefreshSub: Subscription | null = null;

  constructor(
    private router: Router,
    private ngZone: NgZone,
    private kiteService: KiteService,
    private simulatorService: SimulatorService
  ) {}

  private static readonly RESULTS_STORAGE_KEY = 'cognicap_pipeline_results';

  ngOnInit(): void {
    this.loadSavedResults();
    this.loadMarketData();
    this.simulatorService.startPolling(1000);
    this.simulatorSub = this.simulatorService.state$.subscribe(state => {
      if (state) {
        this.simulatorState = state;
      }
    });
    // Refresh market data every 30s
    this.marketRefreshSub = interval(30000).subscribe(() => this.loadMarketData());
  }

  ngOnDestroy(): void {
    this.cancelPipeline();
    this.simulatorService.stopPolling();
    this.simulatorSub?.unsubscribe();
    this.marketRefreshSub?.unsubscribe();
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
    // Reset state
    this.isRunning = true;
    this.isCompleted = false;
    this.activityLog = [];
    this.selectedStocks = [];
    this.pipelineMessage = '';
    this.pipelineSteps.forEach(s => {
      s.status = 'pending';
      s.stocksRemaining = null;
      s.previousCount = null;
    });
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
        this.addLog(data.step, `${data.stocks_remaining} stocks passed`, 'success');
        break;
      }

      case 'final_result':
        this.selectedStocks = data.stocks || [];
        this.pipelineMessage = data.message || '';
        this.startedAt = data.started_at || '';
        this.completedAt = data.completed_at || '';
        this.atrStopLossMultiplier = data.atr_stop_loss_multiplier || 1.5;
        this.isCompleted = true;
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
    this.activityLog.push({
      timestamp: new Date(),
      step,
      message,
      type,
    });
  }

  private saveResults(): void {
    const payload = {
      selectedStocks: this.selectedStocks,
      pipelineMessage: this.pipelineMessage,
      startedAt: this.startedAt,
      completedAt: this.completedAt,
      atrStopLossMultiplier: this.atrStopLossMultiplier,
      pipelineSteps: this.pipelineSteps.map(s => ({
        id: s.id,
        status: s.status,
        stocksRemaining: s.stocksRemaining,
        previousCount: s.previousCount,
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
      if (this.selectedStocks.length > 0 || this.pipelineMessage) {
        this.isCompleted = true;
      }
      if (saved.pipelineSteps) {
        for (const saved_step of saved.pipelineSteps) {
          const step = this.pipelineSteps.find(s => s.id === saved_step.id);
          if (step) {
            step.status = saved_step.status;
            step.stocksRemaining = saved_step.stocksRemaining;
            step.previousCount = saved_step.previousCount;
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
        const quantity = Math.floor(investmentAmount / stock.current_price);

        this.availableFunds = availableFunds;
        this.tradeDetails = {
          symbol: stock.symbol,
          ltp: exits.ltp!,
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

  confirmTrade(): void {
    if (!this.tradeDetails || this.tradeConfirmLoading) return;
    this.tradeConfirmLoading = true;

    const stock = this.selectedStocks.find(s => s.symbol === this.tradeDetails!.symbol);
    this.simulatorService.executeOrder(
      this.tradeDetails.symbol,
      this.tradeDetails.quantity,
      this.tradeDetails.atr,
      this.tradeDetails.trailMultiplier,
      stock?.instrument_token
    ).subscribe({
      next: (result) => {
        this.tradeConfirmLoading = false;
        if (result.success) {
          this.addLog('simulator', result.message || 'Virtual trade executed', 'success');
          this.closeTradeModal();
        } else {
          this.tradeError = result.error || 'Trade failed';
        }
      },
      error: (err) => {
        this.tradeConfirmLoading = false;
        this.tradeError = err?.error?.error || 'Could not execute virtual trade. Is the backend running?';
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

  switchToTradeMode(): void {
    // Placeholder — trade mode not yet implemented
    console.log('Trade mode coming soon');
  }

  resetSimulator(): void {
    this.simulatorService.resetSimulator().subscribe({
      next: () => {
        this.addLog('simulator', 'Simulator reset to ₹1,00,000', 'info');
      }
    });
  }

  researchSectors(): void {
    this.isSectorResearching = true;
    this.simulatorService.researchSectors().subscribe({
      next: (res) => {
        if (res.success && res.sectors) {
          this.sectorLeaderboard = res.sectors;
          this.sectorResearchedAt = res.researched_at || '';
        }
        this.isSectorResearching = false;
      },
      error: () => {
        this.isSectorResearching = false;
      }
    });
  }

  getConvictionColor(score: number): string {
    if (score >= 5) return '#22c55e';
    if (score >= 4) return '#22c55e';
    if (score >= 3) return '#3b82f6';
    if (score >= 2) return '#f97316';
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
      default: return String(this.pipelineSteps.indexOf(step) + 1);
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
}
