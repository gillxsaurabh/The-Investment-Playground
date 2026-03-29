import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MarketBannerComponent } from '../../market-banner/market-banner.component';
import { MarketIndex, Stock } from '../../../services/kite.service';

@Component({
  selector: 'app-header-banner',
  standalone: true,
  imports: [CommonModule, MarketBannerComponent],
  templateUrl: './header-banner.component.html',
  styleUrls: ['./header-banner.component.scss']
})
export class HeaderBannerComponent {
  @Input() userName: string = '';
  @Input() activePage: 'dashboard' | 'trading-agent' | 'discover' | 'positions' | 'automation' | 'account' = 'dashboard';
  @Input() brokerLinked: boolean = false;
  @Input() nifty: MarketIndex | null = null;
  @Input() sensex: MarketIndex | null = null;
  @Input() marketGainers: Stock[] = [];
  @Input() marketLosers: Stock[] = [];
  @Input() isMarketLoading: boolean = false;
  @Input() marketError: string = '';
  @Output() onLogout = new EventEmitter<void>();

  constructor(private router: Router) {}

  navigateTo(page: string): void {
    this.router.navigate([`/${page}`]);
  }

  logout(): void {
    this.onLogout.emit();
  }
}
