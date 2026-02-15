import { Component, OnInit, OnDestroy, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MarketIndex, Stock } from '../../services/kite.service';

@Component({
  selector: 'app-market-banner',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './market-banner.component.html',
  styleUrls: ['./market-banner.component.scss']
})
export class MarketBannerComponent implements OnInit, OnDestroy {
  @Input() nifty: MarketIndex | null = null;
  @Input() sensex: MarketIndex | null = null;
  @Input() marketGainers: Stock[] = [];
  @Input() marketLosers: Stock[] = [];
  @Input() isLoading: boolean = false;
  @Input() error: string = '';

  scrollPosition: number = 0;
  private animationId: number | null = null;

  constructor() {}

  ngOnInit(): void {
    // Animation is handled by CSS, no need for manual scroll
  }

  ngOnDestroy(): void {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
    }
  }

  formatNumber(value: number): string {
    if (!value) return '0';
    return value.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  formatCurrency(value: number): string {
    if (!value) return '₹0';
    const absValue = Math.abs(value);
    const sign = value >= 0 ? '+' : '-';
    
    if (absValue >= 10000000) {
      return `${sign}₹${(absValue / 10000000).toFixed(2)}Cr`;
    } else if (absValue >= 100000) {
      return `${sign}₹${(absValue / 100000).toFixed(2)}L`;
    } else if (absValue >= 1000) {
      return `${sign}₹${(absValue / 1000).toFixed(2)}K`;
    }
    return `${sign}₹${absValue.toFixed(2)}`;
  }

  formatPercentage(value: number): string {
    if (!value) return '0%';
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
  }

  getChangeClass(change: number): string {
    if (change > 0) return 'positive';
    if (change < 0) return 'negative';
    return 'neutral';
  }
}