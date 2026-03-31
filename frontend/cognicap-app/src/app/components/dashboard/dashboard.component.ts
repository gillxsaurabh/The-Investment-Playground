import { Component, OnInit, OnDestroy, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { KiteService, StockAnalysisResponse, MarketIndex, Stock, AuditHolding, AuditSummary } from '../../services/kite.service';
import { SimulatorService, SimulatorState } from '../../services/simulator.service';
import { AuthService } from '../../services/auth.service';
import { DemoService } from '../../services/demo.service';
import { ChatComponent } from '../chat/chat.component';
import { HeaderBannerComponent } from '../shared/header-banner/header-banner.component';
import { StockAuditChartComponent, AuditStep } from './stock-audit-chart.component';
import { forkJoin, interval, Subscription } from 'rxjs';

interface Holding {
  tradingsymbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  day_change: number;
  day_change_percentage: number;
  instrument_token?: number;
}

interface TopPerformer {
  tradingsymbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  pnl_percentage: number;
}

interface AgentStatus {
  stats_agent: 'pending' | 'running' | 'completed';
  company_health_agent: 'pending' | 'running' | 'completed';
  breaking_news_agent: 'pending' | 'running' | 'completed';
  synthesizer: 'pending' | 'running' | 'completed';
  [key: string]: 'pending' | 'running' | 'completed';
}

interface HoldingWithAnalysis extends Holding {
  analysisState: 'not-analyzed' | 'analyzing' | 'analyzed' | 'error';
  analysis?: StockAnalysisResponse;
  error?: string;
  has_saved_analysis?: boolean;
  saved_analysis?: any;
  analysis_saved_at?: string;
  agentStatus?: AgentStatus;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, ChatComponent, HeaderBannerComponent, StockAuditChartComponent],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss', './portfolio-live.scss']
})
export class DashboardComponent implements OnInit, OnDestroy {
  user: any = null;
  brokerLinked = false;
  holdings: HoldingWithAnalysis[] = [];
  summary: any = null;
  topGainers: TopPerformer[] = [];
  topLosers: TopPerformer[] = [];
  isLoading: boolean = true;
  error: string = '';
  
  // Market data
  nifty: MarketIndex | null = null;
  sensex: MarketIndex | null = null;
  marketGainers: Stock[] = [];
  marketLosers: Stock[] = [];
  isMarketLoading: boolean = true;
  marketError: string = '';
  
  // Portfolio update indicator
  isPortfolioUpdating: boolean = false;

  // Track in-flight refresh requests to prevent overlapping calls
  private isMarketRefreshing: boolean = false;
  private isPortfolioRefreshing: boolean = false;
  
  // Health analysis
  selectedStock: HoldingWithAnalysis | null = null;
  isAnalyzingAll: boolean = false;
  analyzeAllProgress: string = '';
  private analyzeAllAbort: AbortController | null = null;
  
  // Open positions widget
  simulatorState: SimulatorState | null = null;
  private simulatorSub: Subscription | null = null;

  // Stock Audit
  auditHoldings: AuditHolding[] = [];
  auditSummary: AuditSummary | null = null;
  auditIsRunning = false;
  auditSteps: AuditStep[] = [];
  auditLastRunAt: string | null = null;
  auditPipelineMessage = '';
  auditSelectedStock: AuditHolding | null = null;
  private auditAbort: AbortController | null = null;

  // Auto refresh subscriptions
  private marketRefreshSubscription: Subscription | null = null;
  private portfolioRefreshSubscription: Subscription | null = null;
  private readonly MARKET_REFRESH_INTERVAL = 30000; // 30 seconds
  private readonly PORTFOLIO_REFRESH_INTERVAL = 15000; // 15 seconds

  constructor(
    private kiteService: KiteService,
    private simulatorService: SimulatorService,
    private authService: AuthService,
    private demoService: DemoService,
    private router: Router,
    private ngZone: NgZone
  ) {}

  ngOnInit(): void {
    this.loadUserData();
    this.loadPortfolioData();
    this.loadMarketData();
    this.loadAuditResults();
    this.startMarketDataAutoRefresh();
    this.startPortfolioDataAutoRefresh();
    this.simulatorService.startPolling(5000);
    this.simulatorSub = this.simulatorService.state$.subscribe(state => {
      if (state) this.simulatorState = state;
    });
  }

  ngOnDestroy(): void {
    this.stopMarketDataAutoRefresh();
    this.stopPortfolioDataAutoRefresh();
    this.simulatorService.stopPolling();
    this.simulatorSub?.unsubscribe();
    this.auditAbort?.abort();
  }

  get openPositionsCount(): number {
    return this.simulatorState?.positions?.length ?? 0;
  }

  get totalUnrealizedPnl(): number {
    return this.simulatorState?.positions?.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0) ?? 0;
  }

  get recentTrades(): any[] {
    return (this.simulatorState?.trade_history ?? []).slice(0, 5);
  }

  private startMarketDataAutoRefresh(): void {
    // Auto-refresh market data every 30 seconds
    this.marketRefreshSubscription = interval(this.MARKET_REFRESH_INTERVAL)
      .subscribe(() => {
        // Only skip if a previous refresh is still in-flight
        if (!this.isMarketRefreshing) {
          this.loadMarketData();
        }
      });
  }

  private stopMarketDataAutoRefresh(): void {
    if (this.marketRefreshSubscription) {
      this.marketRefreshSubscription.unsubscribe();
      this.marketRefreshSubscription = null;
    }
  }

  private startPortfolioDataAutoRefresh(): void {
    // Auto-refresh portfolio data every 15 seconds for live experience
    this.portfolioRefreshSubscription = interval(this.PORTFOLIO_REFRESH_INTERVAL)
      .subscribe(() => {
        // Only skip if a previous refresh is still in-flight
        if (!this.isPortfolioRefreshing) {
          console.log('Auto-refreshing portfolio data...');
          this.loadPortfolioData();
        }
      });
  }

  private stopPortfolioDataAutoRefresh(): void {
    if (this.portfolioRefreshSubscription) {
      this.portfolioRefreshSubscription.unsubscribe();
      this.portfolioRefreshSubscription = null;
    }
  }

  loadUserData(): void {
    this.authService.user$.subscribe(user => { this.user = user; });
    this.authService.brokerLinked$.subscribe(linked => {
      this.brokerLinked = linked;
      // When broker becomes linked mid-session, kick off a portfolio load
      if (linked && this.holdings.length === 0 && !this.isPortfolioRefreshing) {
        this.loadPortfolioData();
        this.loadAuditResults();
      }
    });
    // Read initial value synchronously from the subject
    this.brokerLinked = this.authService.isBrokerLinked;
  }

  loadPortfolioData(): void {
    // Tier 1 users have no broker — skip portfolio calls, show link prompt
    if (!this.brokerLinked) {
      this.isLoading = false;
      this.isPortfolioRefreshing = false;
      return;
    }

    // Set loading state only if this is the first load
    const isFirstLoad = this.holdings.length === 0 && !this.summary;
    if (isFirstLoad) {
      this.isLoading = true;
    } else {
      this.isPortfolioUpdating = true;
    }

    this.isPortfolioRefreshing = true;
    this.error = '';

    // Load holdings with analysis state, preserving in-progress analysis
    this.kiteService.getHoldings().subscribe({
      next: (response) => {
        if (response.success) {
          // Build a map of current holdings that are being analyzed
          const analyzingHoldings = new Map<string, HoldingWithAnalysis>();
          this.holdings.forEach(h => {
            if (h.analysisState === 'analyzing') {
              analyzingHoldings.set(h.tradingsymbol, h);
            }
          });

          this.holdings = (response.holdings || []).map(holding => {
            // Preserve analysis state for holdings currently being analyzed
            const existing = analyzingHoldings.get(holding.tradingsymbol);
            if (existing) {
              return {
                ...holding,
                analysisState: existing.analysisState,
                analysis: existing.analysis,
                agentStatus: existing.agentStatus,
                error: existing.error,
              };
            }
            return {
              ...holding,
              analysisState: holding.has_saved_analysis ? 'analyzed' as const : 'not-analyzed' as const,
              analysis: holding.has_saved_analysis ? holding.saved_analysis : undefined
            };
          });
        } else {
          this.error = response.error || 'Failed to load holdings';
        }
        
        // Clear update indicators
        if (isFirstLoad) {
          this.isLoading = false;
        }
        this.isPortfolioUpdating = false;
        this.isPortfolioRefreshing = false;
      },
      error: (err) => {
        this.error = 'Failed to load holdings. Please try again.';
        console.error('Holdings error:', err);

        // Clear update indicators
        if (isFirstLoad) {
          this.isLoading = false;
        }
        this.isPortfolioUpdating = false;
        this.isPortfolioRefreshing = false;
      }
    });

    // Load summary
    this.kiteService.getPortfolioSummary().subscribe({
      next: (response) => {
        if (response.success) {
          this.summary = response.summary;
          console.log('Portfolio updated:', response.note || 'Live data loaded');
        }
        // Don't set loading to false here since holdings might still be loading
      },
      error: (err) => {
        console.error('Summary error:', err);
        // Don't set loading to false here since holdings might still be loading
      }
    });

    // Load top performers
    this.kiteService.getTopPerformers().subscribe({
      next: (response) => {
        if (response.success) {
          this.topGainers = response.top_gainers || [];
          this.topLosers = response.top_losers || [];
        }
      },
      error: (err) => {
        console.error('Top performers error:', err);
      }
    });
  }

  loadMarketData(): void {
    // Set loading state only if this is the first load
    if (!this.nifty && !this.sensex && this.marketGainers.length === 0) {
      this.isMarketLoading = true;
    }

    this.isMarketRefreshing = true;
    this.marketError = '';

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
        this.isMarketRefreshing = false;
      },
      error: (err) => {
        this.marketError = 'Failed to load market data.';
        this.isMarketLoading = false;
        this.isMarketRefreshing = false;
        console.error('Market data error:', err);
      }
    });
  }

  refreshData(): void {
    this.loadPortfolioData();
    this.loadMarketData();
  }

  logout(): void {
    this.authService.logout();
    this.demoService.exitDemo();
  }

  navigateToDiscover(): void {
    this.router.navigate(['/discover']);
  }

  navigateToSellAudit(): void {
    this.router.navigate(['/discover'], { queryParams: { mode: 'sell' } });
  }

  navigateToPositions(): void {
    this.router.navigate(['/positions']);
  }

  navigateToAutomation(): void {
    this.router.navigate(['/automation']);
  }

  getPnlClass(pnl: number): string {
    return pnl >= 0 ? 'positive' : 'negative';
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2
    }).format(value);
  }

  formatPercentage(value: number): string {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  }

  // Health Analysis Methods
  async analyzeAllStocks(): Promise<void> {
    this.isAnalyzingAll = true;
    this.analyzeAllAbort = new AbortController();
    const unanalyzed = this.holdings.filter(h => h.analysisState !== 'analyzed');

    if (unanalyzed.length === 0) {
      this.analyzeAllProgress = 'All stocks already analyzed.';
      setTimeout(() => {
        this.isAnalyzingAll = false;
        this.analyzeAllProgress = '';
      }, 2000);
      return;
    }

    for (let i = 0; i < unanalyzed.length; i++) {
      if (this.analyzeAllAbort.signal.aborted) break;
      this.analyzeAllProgress = `Analyzing ${i + 1}/${unanalyzed.length}: ${unanalyzed[i].tradingsymbol}`;
      await this.analyzeStockStream(unanalyzed[i], this.analyzeAllAbort.signal);
    }

    if (this.analyzeAllAbort.signal.aborted) {
      this.analyzeAllProgress = 'Analysis cancelled.';
    } else {
      const analyzed = unanalyzed.filter(h => h.analysisState === 'analyzed').length;
      this.analyzeAllProgress = `Completed: ${analyzed}/${unanalyzed.length} stocks analyzed`;
    }

    setTimeout(() => {
      this.isAnalyzingAll = false;
      this.analyzeAllProgress = '';
      this.analyzeAllAbort = null;
    }, 3000);
  }

  cancelAnalysis(): void {
    if (this.analyzeAllAbort) {
      this.analyzeAllAbort.abort();
      // Reset any holdings still in 'analyzing' state
      this.holdings.forEach(h => {
        if (h.analysisState === 'analyzing') {
          h.analysisState = h.has_saved_analysis ? 'analyzed' : 'not-analyzed';
          h.agentStatus = undefined;
        }
      });
    }
  }

  analyzeStock(holding: HoldingWithAnalysis): void {
    this.analyzeStockStream(holding);
  }

  private async analyzeStockStream(holding: HoldingWithAnalysis, signal?: AbortSignal): Promise<void> {
    holding.analysisState = 'analyzing';
    holding.error = undefined;
    holding.agentStatus = {
      stats_agent: 'pending',
      company_health_agent: 'pending',
      breaking_news_agent: 'pending',
      synthesizer: 'pending',
    };

    let timeoutId: number | undefined;
    const STREAM_TIMEOUT = 120000; // 2 minutes timeout

    try {
      const jwtToken = localStorage.getItem('jwt_access_token') || '';

      // Set up timeout
      timeoutId = setTimeout(() => {
        console.error('Stream timeout after 2 minutes');
        holding.analysisState = 'error';
        holding.error = 'Analysis timed out. Please try again.';
        holding.agentStatus = undefined;
      }, STREAM_TIMEOUT);

      const response = await fetch('/api/analyze-stock-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${jwtToken}`,
        },
        body: JSON.stringify({
          symbol: holding.tradingsymbol,
          instrument_token: holding.instrument_token,
        }),
        signal,
      });

      if (!response.ok || !response.body) {
        throw new Error('Stream request failed');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      // Keep eventType in outer scope so it persists across chunks
      let currentEventType = '';

      const processLines = (lines: string[]) => {
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith('data: ') && currentEventType) {
            try {
              const data = JSON.parse(line.slice(6));
              const evt = currentEventType;
              this.ngZone.run(() => this.handleSSEEvent(holding, evt, data));
            } catch (parseError) {
              console.warn('Failed to parse SSE data:', line.slice(6));
            }
            currentEventType = '';
          } else if (line.trim() === '') {
            // Empty line is SSE event delimiter — reset if we had a dangling event type
            // (shouldn't happen with well-formed SSE, but defensive)
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          // Process any remaining buffer when stream ends
          if (buffer.trim()) {
            processLines(buffer.split('\n'));
          }
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        processLines(lines);
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('Stream analysis cancelled');
        return;
      }
      
      console.error('Stream analysis error:', err);
      holding.analysisState = 'error';
      holding.error = err.message || 'Failed to analyze stock. Please try again.';
      holding.agentStatus = undefined;
    } finally {
      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
      }
    }
  }

  private handleSSEEvent(holding: HoldingWithAnalysis, event: string, data: any): void {
    console.log(`SSE Event: ${event}`, data); // Debug logging
    
    if (event === 'agent_start' && holding.agentStatus) {
      holding.agentStatus[data.agent] = 'running';
    } else if (event === 'agent_complete' && holding.agentStatus) {
      holding.agentStatus[data.agent] = 'completed';
    } else if (event === 'complete') {
      console.log('Analysis complete, updating holding state'); // Debug
      holding.analysisState = 'analyzed';
      holding.analysis = data;
      holding.has_saved_analysis = true;
      holding.agentStatus = undefined;
    } else if (event === 'end') {
      console.log('SSE stream ended'); // Debug
      // Stream has ended naturally
    }
  }

  agentDisplayName(agent: string): string {
    const names: Record<string, string> = {
      stats_agent: 'Stats Agent',
      company_health_agent: 'Company Health',
      breaking_news_agent: 'Breaking News',
      synthesizer: 'Synthesizer',
    };
    return names[agent] || agent;
  }

  openStockModal(holding: HoldingWithAnalysis): void {
    this.selectedStock = holding;
  }

  closeStockModal(): void {
    this.selectedStock = null;
  }

  getAnalyzedCount(): number {
    return this.holdings.filter(h => h.has_saved_analysis).length;
  }

  getOverallScore(analysis: any): number | undefined {
    return analysis?.overall_score ?? analysis?.score;
  }

  getScoreColor(score: number): string {
    if (score >= 4) return '#22c55e';
    if (score >= 3) return '#eab308';
    if (score >= 2) return '#f97316';
    return '#ef4444';
  }

  formatDate(isoDate: string): string {
    const date = new Date(isoDate);
    return date.toLocaleString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  // ── Stock Audit ───────────────────────────────────────────────────────────

  loadAuditResults(): void {
    this.kiteService.getAuditResults().subscribe({
      next: (resp) => {
        if (resp.success && resp.results.length > 0) {
          this.auditHoldings = resp.results.map(r => ({ ...r.data, saved_at: r.saved_at }));
          this.auditLastRunAt = resp.results[0]?.saved_at ?? null;
          this.auditSummary = this.computeAuditSummary(this.auditHoldings);
        }
      },
      error: () => { /* no cached results — silent */ },
    });
  }

  private computeAuditSummary(holdings: AuditHolding[]): AuditSummary {
    const summary: AuditSummary = { total: holdings.length, healthy: 0, stable: 0, watch: 0, critical: 0, avg_score: 0 };
    let scoreSum = 0;
    for (const h of holdings) {
      if (h.health_label === 'HEALTHY')  summary.healthy++;
      else if (h.health_label === 'STABLE')   summary.stable++;
      else if (h.health_label === 'WATCH')    summary.watch++;
      else if (h.health_label === 'CRITICAL') summary.critical++;
      scoreSum += h.health_score;
    }
    summary.avg_score = holdings.length > 0 ? +(scoreSum / holdings.length).toFixed(1) : 0;
    return summary;
  }

  runAudit(): void {
    if (!this.brokerLinked) {
      this.router.navigate(['/connect-kite']);
      return;
    }
    if (this.auditIsRunning) return;
    this.auditIsRunning = true;
    this.auditSteps = [];
    this.auditPipelineMessage = 'Starting audit…';
    this.auditAbort = new AbortController();

    const jwt = localStorage.getItem('jwt_access_token') || '';

    fetch('/api/audit/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${jwt}` },
      body: JSON.stringify({}),
      signal: this.auditAbort.signal,
    }).then(resp => {
      if (!resp.ok || !resp.body) throw new Error('Audit request failed');
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';

      const pump = (): Promise<void> =>
        reader.read().then(({ done, value }) => {
          if (done) {
            if (buffer.trim()) this.processAuditLines(buffer.split('\n'), currentEvent);
            this.ngZone.run(() => { this.auditIsRunning = false; this.auditPipelineMessage = ''; });
            return;
          }
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('event: ')) { currentEvent = line.slice(7).trim(); }
            else if (line.startsWith('data: ') && currentEvent) {
              try {
                const data = JSON.parse(line.slice(6));
                const evt = currentEvent;
                this.ngZone.run(() => this.handleAuditEvent(evt, data));
              } catch {}
              currentEvent = '';
            }
          }
          return pump();
        });

      return pump();
    }).catch((err: any) => {
      if (err?.name !== 'AbortError') console.error('Audit SSE error', err);
      this.ngZone.run(() => { this.auditIsRunning = false; this.auditPipelineMessage = ''; });
    });
  }

  private processAuditLines(lines: string[], currentEvent: string): void {
    for (const line of lines) {
      if (line.startsWith('event: ')) { currentEvent = line.slice(7).trim(); }
      else if (line.startsWith('data: ') && currentEvent) {
        try { const data = JSON.parse(line.slice(6)); this.ngZone.run(() => this.handleAuditEvent(currentEvent, data)); } catch {}
        currentEvent = '';
      }
    }
  }

  private handleAuditEvent(event: string, data: any): void {
    if (event === 'step_start') {
      this.auditPipelineMessage = data.role || '';
      const existing = this.auditSteps.find(s => s.step === data.step);
      if (existing) { existing.status = 'running'; }
      else { this.auditSteps.push({ step: data.step, agent: data.agent, role: data.role, status: 'running' }); }
    } else if (event === 'step_log') {
      this.auditPipelineMessage = data.message || '';
    } else if (event === 'step_complete') {
      const s = this.auditSteps.find(st => st.step === data.step);
      if (s) { s.status = 'completed'; s.duration_ms = data.duration_ms; }
    } else if (event === 'final_result') {
      this.auditHoldings = (data.holdings || []).map((h: AuditHolding) => ({ ...h, saved_at: data.saved_at }));
      this.auditLastRunAt = data.saved_at ?? new Date().toISOString();
      this.auditSummary = this.computeAuditSummary(this.auditHoldings);
      this.auditIsRunning = false;
      this.auditPipelineMessage = '';
    }
  }

  openAuditStockModal(holding: AuditHolding): void {
    this.auditSelectedStock = holding;
  }

  closeAuditStockModal(): void {
    this.auditSelectedStock = null;
  }

  // Market helper methods
  formatNumber(value: number): string {
    return value.toLocaleString('en-IN');
  }

  getChangeClass(value: number): string {
    if (value > 0) return 'positive';
    if (value < 0) return 'negative';
    return 'neutral';
  }
}
