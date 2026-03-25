import { Component, OnInit, OnDestroy, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { KiteService, StockAnalysisResponse, MarketIndex, Stock } from '../../services/kite.service';
import { DemoService } from '../../services/demo.service';
import { ChatComponent } from '../chat/chat.component';
import { HeaderBannerComponent } from '../shared/header-banner/header-banner.component';
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
  imports: [CommonModule, ChatComponent, HeaderBannerComponent],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss', './portfolio-live.scss']
})
export class DashboardComponent implements OnInit, OnDestroy {
  user: any = null;
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
  
  // Auto refresh subscriptions
  private marketRefreshSubscription: Subscription | null = null;
  private portfolioRefreshSubscription: Subscription | null = null;
  private readonly MARKET_REFRESH_INTERVAL = 30000; // 30 seconds
  private readonly PORTFOLIO_REFRESH_INTERVAL = 15000; // 15 seconds

  constructor(
    private kiteService: KiteService,
    private demoService: DemoService,
    private router: Router,
    private ngZone: NgZone
  ) {}

  ngOnInit(): void {
    this.loadUserData();
    this.loadPortfolioData();
    this.loadMarketData();
    this.startMarketDataAutoRefresh();
    this.startPortfolioDataAutoRefresh();
  }

  ngOnDestroy(): void {
    this.stopMarketDataAutoRefresh();
    this.stopPortfolioDataAutoRefresh();
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
    this.kiteService.user$.subscribe(user => {
      this.user = user;
    });
  }

  loadPortfolioData(): void {
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
    this.kiteService.logout();
    this.demoService.exitDemo();
    this.router.navigate(['/']);
  }

  navigateToTradingAgent(): void {
    this.router.navigate(['/trading-agent']);
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
      const accessToken = localStorage.getItem('access_token') || '';
      
      // Set up timeout  
      timeoutId = setTimeout(() => {
        console.error('Stream timeout after 2 minutes');
        holding.analysisState = 'error';
        holding.error = 'Analysis timed out. Please try again.';
        holding.agentStatus = undefined;
      }, STREAM_TIMEOUT);

      const response = await fetch('/api/analyze-stock-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_token: accessToken,
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
