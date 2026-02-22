import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { KiteService, StockAnalysisResponse } from '../../services/kite.service';

interface HoldingWithAnalysis {
  tradingsymbol: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  instrument_token?: number;
  exchange?: string;
  analysisState: 'not-analyzed' | 'analyzing' | 'analyzed' | 'error';
  analysis?: StockAnalysisResponse;
  error?: string;
  has_saved_analysis?: boolean;
  saved_analysis?: any;
  analysis_saved_at?: string;
}

@Component({
  selector: 'app-health',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './health.component.html',
  styleUrls: ['./health.component.scss']
})
export class HealthComponent implements OnInit {
  holdings: HoldingWithAnalysis[] = [];
  isLoadingHoldings: boolean = false;
  isAnalyzingAll: boolean = false;
  analyzeAllProgress: string = '';
  error: string = '';
  expandedStock: string | null = null;

  constructor(private kiteService: KiteService) {}

  ngOnInit(): void {
    this.loadHoldings();
  }

  loadHoldings(): void {
    this.isLoadingHoldings = true;
    this.error = '';

    this.kiteService.getHoldings().subscribe({
      next: (response) => {
        if (response.success && response.holdings) {
          this.holdings = response.holdings.map(holding => ({
            ...holding,
            analysisState: holding.has_saved_analysis ? 'analyzed' as const : 'not-analyzed' as const,
            analysis: holding.has_saved_analysis ? holding.saved_analysis : undefined
          }));
        } else {
          this.error = response.error || 'Failed to load holdings';
        }
        this.isLoadingHoldings = false;
      },
      error: (err) => {
        this.error = 'Failed to load holdings. Please try again.';
        console.error('Holdings error:', err);
        this.isLoadingHoldings = false;
      }
    });
  }

  analyzeAllStocks(): void {
    this.isAnalyzingAll = true;
    this.analyzeAllProgress = 'Starting analysis...';

    // Update all holdings to analyzing state
    this.holdings.forEach(holding => {
      holding.analysisState = 'analyzing';
    });

    this.kiteService.analyzeAllStocks().subscribe({
      next: (response) => {
        if (response.success) {
          this.analyzeAllProgress = `Completed: ${response.successful_analyses}/${response.total_stocks} stocks analyzed`;
          
          // Update holdings with results
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
        
        // Reset state
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

  refreshHoldings(): void {
    this.loadHoldings();
  }

  toggleExpand(symbol: string): void {
    this.expandedStock = this.expandedStock === symbol ? null : symbol;
  }

  isExpanded(symbol: string): boolean {
    return this.expandedStock === symbol;
  }

  getAnalyzedCount(): number {
    return this.holdings.filter(h => h.has_saved_analysis).length;
  }

  getOverallScore(analysis: StockAnalysisResponse): number {
    return analysis.overall_score ?? analysis.score ?? 0;
  }

  getVerdict(analysis: StockAnalysisResponse): string {
    return analysis.verdict || '';
  }

  getVerdictAction(verdict: string): string {
    const actions = ['Strong Buy', 'Buy', 'Accumulate', 'Hold', 'Reduce', 'Exit'];
    for (const action of actions) {
      if (verdict.toLowerCase().startsWith(action.toLowerCase())) {
        return action;
      }
      if (verdict.includes('—')) {
        const before = verdict.split('—')[0].trim();
        if (before.toLowerCase() === action.toLowerCase()) return action;
      }
    }
    return '';
  }

  getVerdictActionClass(verdict: string): string {
    const action = this.getVerdictAction(verdict).toLowerCase();
    if (['strong buy', 'buy', 'accumulate'].includes(action)) return 'verdict-bullish';
    if (action === 'hold') return 'verdict-neutral';
    return 'verdict-bearish';
  }

  hasNewFormat(analysis: StockAnalysisResponse): boolean {
    return !!analysis.agents;
  }

  getScoreColor(score: number): string {
    if (score >= 4) return '#10b981'; // Green
    if (score >= 2.5) return '#f59e0b'; // Yellow
    return '#ef4444'; // Red
  }

  getScoreBadgeClass(score: number): string {
    if (score >= 4) return 'badge-green';
    if (score >= 2.5) return 'badge-yellow';
    return 'badge-red';
  }

  getScoreLabel(score: number): string {
    if (score >= 4.5) return 'Excellent';
    if (score >= 4) return 'Good';
    if (score >= 3) return 'Average';
    if (score >= 2) return 'Below Average';
    return 'Poor';
  }

  getAgentIcon(agentName: string): string {
    switch (agentName) {
      case 'stats_agent': return '📊';
      case 'company_health_agent': return '🏢';
      case 'breaking_news_agent': return '📰';
      default: return '🔍';
    }
  }

  getAgentLabel(agentName: string): string {
    switch (agentName) {
      case 'stats_agent': return 'Technical Analysis';
      case 'company_health_agent': return 'Company Health';
      case 'breaking_news_agent': return 'News & Sentiment';
      default: return agentName;
    }
  }

  isAgentFailed(agent: any): boolean {
    if (!agent) return true;
    return agent.explanation?.includes('failed') || agent.explanation?.includes('could not be completed');
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

  formatCurrency(amount: number): string {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount);
  }
}
