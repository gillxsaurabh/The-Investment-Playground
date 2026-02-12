import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { KiteService } from '../../services/kite.service';
import { ChatComponent } from '../chat/chat.component';
import { MarketComponent } from '../market/market.component';
import { HealthComponent } from '../health/health.component';

interface Holding {
  tradingsymbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  day_change: number;
  day_change_percentage: number;
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

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, ChatComponent, MarketComponent, HealthComponent],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent implements OnInit {
  user: any = null;
  holdings: Holding[] = [];
  summary: any = null;
  topGainers: TopPerformer[] = [];
  topLosers: TopPerformer[] = [];
  isLoading: boolean = true;
  error: string = '';
  activeTab: string = 'portfolio';

  constructor(
    private kiteService: KiteService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.loadUserData();
    this.loadPortfolioData();
  }

  loadUserData(): void {
    this.kiteService.user$.subscribe(user => {
      this.user = user;
    });
  }

  loadPortfolioData(): void {
    this.isLoading = true;
    this.error = '';

    // Load holdings
    this.kiteService.getHoldings().subscribe({
      next: (response) => {
        if (response.success) {
          this.holdings = response.holdings || [];
        } else {
          this.error = response.error || 'Failed to load holdings';
        }
      },
      error: (err) => {
        this.error = 'Failed to load holdings. Please try again.';
        console.error('Holdings error:', err);
      }
    });

    // Load summary
    this.kiteService.getPortfolioSummary().subscribe({
      next: (response) => {
        if (response.success) {
          this.summary = response.summary;
        }
        this.isLoading = false;
      },
      error: (err) => {
        this.isLoading = false;
        console.error('Summary error:', err);
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

  refreshData(): void {
    this.loadPortfolioData();
  }

  switchTab(tab: string): void {
    this.activeTab = tab;
  }

  isPortfolioTab(): boolean {
    return this.activeTab === 'portfolio';
  }

  isMarketTab(): boolean {
    return this.activeTab === 'market';
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
}
