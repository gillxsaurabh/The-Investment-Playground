import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { KiteService, StockAnalysisResponse, MarketIndex, Stock } from '../../services/kite.service';
import { ChatComponent } from '../chat/chat.component';
import { MarketBannerComponent } from '../market-banner/market-banner.component';
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

interface HoldingWithAnalysis extends Holding {
  analysisState: 'not-analyzed' | 'analyzing' | 'analyzed' | 'error';
  analysis?: StockAnalysisResponse;
  error?: string;
  has_saved_analysis?: boolean;
  saved_analysis?: any;
  analysis_saved_at?: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, ChatComponent, MarketBannerComponent],
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
  
  // Health analysis
  selectedStock: HoldingWithAnalysis | null = null;
  isAnalyzingAll: boolean = false;
  analyzeAllProgress: string = '';
  
  // Auto refresh subscriptions
  private marketRefreshSubscription: Subscription | null = null;
  private portfolioRefreshSubscription: Subscription | null = null;
  private readonly MARKET_REFRESH_INTERVAL = 30000; // 30 seconds
  private readonly PORTFOLIO_REFRESH_INTERVAL = 15000; // 15 seconds

  constructor(
    private kiteService: KiteService,
    private router: Router
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
        // Only refresh if we're not currently loading and no errors
        if (!this.isMarketLoading && !this.marketError) {
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
        // Always refresh portfolio data (no conditions) for live experience
        console.log('Auto-refreshing portfolio data...');
        this.loadPortfolioData();
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
    
    this.error = '';

    // Load holdings with analysis state
    this.kiteService.getHoldings().subscribe({
      next: (response) => {
        if (response.success) {
          this.holdings = (response.holdings || []).map(holding => ({
            ...holding,
            analysisState: holding.has_saved_analysis ? 'analyzed' as const : 'not-analyzed' as const,
            analysis: holding.has_saved_analysis ? holding.saved_analysis : undefined
          }));
        } else {
          this.error = response.error || 'Failed to load holdings';
        }
        
        // Clear update indicators
        if (isFirstLoad) {
          this.isLoading = false;
        }
        this.isPortfolioUpdating = false;
      },
      error: (err) => {
        this.error = 'Failed to load holdings. Please try again.';
        console.error('Holdings error:', err);
        
        // Clear update indicators
        if (isFirstLoad) {
          this.isLoading = false;
        }
        this.isPortfolioUpdating = false;
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
      },
      error: (err) => {
        this.marketError = 'Failed to load market data.';
        this.isMarketLoading = false;
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
    this.router.navigate(['/login']);
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
  analyzeAllStocks(): void {
    this.isAnalyzingAll = true;
    this.analyzeAllProgress = 'Starting analysis...';

    this.holdings.forEach(holding => {
      holding.analysisState = 'analyzing';
    });

    this.kiteService.analyzeAllStocks().subscribe({
      next: (response) => {
        if (response.success) {
          this.analyzeAllProgress = `Completed: ${response.successful_analyses}/${response.total_stocks} stocks analyzed`;
          
          response.results.forEach((result: any) => {
            const holding = this.holdings.find(h => h.tradingsymbol === result.symbol);
            if (holding) {
              if (result.success && result.analysis) {
                holding.analysisState = 'analyzed';
                holding.analysis = result.analysis;
                holding.has_saved_analysis = true;
              } else {
                holding.analysisState = 'error';
                holding.error = result.error || 'Analysis failed';
              }
            }
          });
          
          setTimeout(() => {
            this.isAnalyzingAll = false;
            this.analyzeAllProgress = '';
          }, 3000);
        } else {
          this.analyzeAllProgress = `Failed: ${response.error}`;
          this.holdings.forEach(holding => {
            holding.analysisState = holding.has_saved_analysis ? 'analyzed' : 'not-analyzed';
          });
          
          setTimeout(() => {
            this.isAnalyzingAll = false;
            this.analyzeAllProgress = '';
          }, 3000);
        }
      },
      error: (err) => {
        this.analyzeAllProgress = 'Analysis failed. Please try again.';
        console.error('Analyze all error:', err);
        
        this.holdings.forEach(holding => {
          holding.analysisState = holding.has_saved_analysis ? 'analyzed' : 'not-analyzed';
        });
        
        setTimeout(() => {
          this.isAnalyzingAll = false;
          this.analyzeAllProgress = '';
        }, 3000);
      }
    });
  }

  analyzeStock(holding: HoldingWithAnalysis): void {
    holding.analysisState = 'analyzing';
    holding.error = undefined;

    this.kiteService.analyzeStock(holding.tradingsymbol, holding.instrument_token).subscribe({
      next: (response) => {
        if (response.success) {
          holding.analysisState = 'analyzed';
          holding.analysis = response;
          holding.has_saved_analysis = true;
        } else {
          holding.analysisState = 'error';
          holding.error = response.error || 'Analysis failed';
        }
      },
      error: (err) => {
        holding.analysisState = 'error';
        holding.error = 'Failed to analyze stock. Please try again.';
        console.error('Analysis error:', err);
      }
    });
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

  getScoreColor(score: number): string {
    if (score >= 4) return '#10b981';
    if (score >= 2.5) return '#f59e0b';
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
