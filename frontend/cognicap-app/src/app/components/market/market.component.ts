import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { KiteService, MarketIndex, Stock } from '../../services/kite.service';
import { forkJoin } from 'rxjs';

@Component({
  selector: 'app-market',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './market.component.html',
  styleUrls: ['./market.component.scss']
})
export class MarketComponent implements OnInit {
  nifty: MarketIndex | null = null;
  sensex: MarketIndex | null = null;
  topGainers: Stock[] = [];
  topLosers: Stock[] = [];
  isLoading: boolean = true;
  error: string = '';

  constructor(private kiteService: KiteService) {}

  ngOnInit(): void {
    console.log('MarketComponent initialized');
    this.loadMarketData();
  }

  loadMarketData(): void {
    console.log('MarketComponent: Loading market data...');
    this.isLoading = true;
    this.error = '';

    // Load both APIs together
    forkJoin({
      indices: this.kiteService.getMarketIndices(),
      stocks: this.kiteService.getTopStocks()
    }).subscribe({
      next: (results) => {
        console.log('MarketComponent: API results received', results);
        
        // Process indices
        if (results.indices.success) {
          this.nifty = results.indices.nifty || null;
          this.sensex = results.indices.sensex || null;
          console.log('MarketComponent: Nifty data:', this.nifty);
          console.log('MarketComponent: Sensex data:', this.sensex);
        }
        
        // Process stocks
        if (results.stocks.success) {
          this.topGainers = results.stocks.top_gainers || [];
          this.topLosers = results.stocks.top_losers || [];
          console.log('MarketComponent: Top gainers:', this.topGainers.length);
          console.log('MarketComponent: Top losers:', this.topLosers.length);
        }
        
        this.isLoading = false;
        console.log('MarketComponent: Loading complete, isLoading =', this.isLoading);
      },
      error: (err) => {
        console.error('MarketComponent: Error loading data', err);
        this.error = 'Failed to load market data. Please try again.';
        this.isLoading = false;
      }
    });
  }

  refreshData(): void {
    this.loadMarketData();
  }

  formatCurrency(value: number): string {
    return '₹' + value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  formatNumber(value: number): string {
    return value.toLocaleString('en-IN');
  }

  formatPercentage(value: number): string {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
  }

  getChangeClass(value: number): string {
    if (value > 0) return 'positive';
    if (value < 0) return 'negative';
    return 'neutral';
  }
}
