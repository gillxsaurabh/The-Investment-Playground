import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { KiteService, MarketIndex, Stock } from '../../services/kite.service';
import { SimulatorService, SimulatorState, SimulatorPosition, SimulatorTradeHistory } from '../../services/simulator.service';
import { AuthService, User } from '../../services/auth.service';
import { DemoService } from '../../services/demo.service';
import { HeaderBannerComponent } from '../shared/header-banner/header-banner.component';
import { PositionsChartComponent } from './positions-chart.component';
import { forkJoin, interval, Subscription } from 'rxjs';

@Component({
  selector: 'app-positions',
  standalone: true,
  imports: [CommonModule, FormsModule, HeaderBannerComponent, PositionsChartComponent],
  templateUrl: './positions.component.html',
  styleUrls: ['./positions.component.scss']
})
export class PositionsComponent implements OnInit, OnDestroy {
  simulatorState: SimulatorState | null = null;
  tradingMode: 'simulator' | 'live' = 'simulator';
  isExiting: { [tradeId: string]: boolean } = {};

  // Reset modal
  showResetModal = false;
  resetCapital = 100000;

  // Mode switch
  showModeConfirmDialog = false;
  liveConfirmPhrase = '';
  readonly LIVE_CONFIRM_PHRASE = 'I understand this uses real money';

  // Market data
  user: User | null = null;
  brokerLinked = false;
  nifty: MarketIndex | null = null;
  sensex: MarketIndex | null = null;
  marketGainers: Stock[] = [];
  marketLosers: Stock[] = [];
  isMarketLoading = false;
  marketError = '';

  activeTab: 'positions' | 'history' = 'positions';

  private simulatorSub: Subscription | null = null;
  private marketRefreshSub: Subscription | null = null;

  constructor(
    private router: Router,
    private kiteService: KiteService,
    private simulatorService: SimulatorService,
    private authService: AuthService,
    private demoService: DemoService
  ) {}

  ngOnInit(): void {
    this.authService.user$.subscribe(u => { this.user = u; });
    this.authService.brokerLinked$.subscribe(l => { this.brokerLinked = l; });
    this.loadMarketData();
    this.marketRefreshSub = interval(30000).subscribe(() => this.loadMarketData());
    this.simulatorService.startPolling(3000);
    this.simulatorSub = this.simulatorService.state$.subscribe(state => {
      if (state) this.simulatorState = state;
    });
    this.simulatorService.tradingMode$.subscribe(mode => { this.tradingMode = mode; });
  }

  ngOnDestroy(): void {
    this.simulatorService.stopPolling();
    this.simulatorSub?.unsubscribe();
    this.marketRefreshSub?.unsubscribe();
  }

  private loadMarketData(): void {
    this.isMarketLoading = true;
    forkJoin({ indices: this.kiteService.getMarketIndices(), stocks: this.kiteService.getTopStocks() }).subscribe({
      next: r => {
        if (r.indices.success) { this.nifty = r.indices.nifty ?? null; this.sensex = r.indices.sensex ?? null; }
        if (r.stocks.success) { this.marketGainers = r.stocks.top_gainers ?? []; this.marketLosers = r.stocks.top_losers ?? []; }
        this.isMarketLoading = false;
      },
      error: () => { this.isMarketLoading = false; }
    });
  }

  closePosition(tradeId: string): void {
    if (this.isExiting[tradeId]) return;
    this.isExiting[tradeId] = true;
    this.simulatorService.closePosition(tradeId).subscribe({
      next: () => { delete this.isExiting[tradeId]; },
      error: () => { delete this.isExiting[tradeId]; }
    });
  }

  resetSimulator(): void {
    this.simulatorService.resetSimulator(this.resetCapital).subscribe({
      next: () => { this.showResetModal = false; },
      error: () => {}
    });
  }

  switchToLive(): void {
    if (this.liveConfirmPhrase !== this.LIVE_CONFIRM_PHRASE) return;
    this.simulatorService.setTradingMode('live', true).subscribe({
      next: () => { this.showModeConfirmDialog = false; this.liveConfirmPhrase = ''; },
      error: () => {}
    });
  }

  switchToSimulator(): void {
    this.simulatorService.setTradingMode('simulator').subscribe({ error: () => {} });
  }

  computeTrailStatus(pos: SimulatorPosition): string {
    return this.simulatorService.computeTrailStatus(pos);
  }

  getTrailStatusClass(pos: SimulatorPosition): string {
    const s = this.computeTrailStatus(pos);
    return s === 'RUNAWAY' ? 'trail-run' : s === 'CRITICAL' ? 'trail-crit' : s === 'STALLED' ? 'trail-stall' : 'trail-hold';
  }

  get openPositions(): SimulatorPosition[] {
    return this.simulatorState?.positions ?? [];
  }

  get tradeHistory(): SimulatorTradeHistory[] {
    return this.simulatorState?.trade_history ?? [];
  }

  get totalUnrealized(): number {
    return this.openPositions.reduce((sum, p) => sum + (p.unrealized_pnl ?? 0), 0);
  }

  get totalBalance(): number {
    return this.simulatorState?.account_summary?.current_balance ?? 0;
  }

  get initialCapital(): number {
    return this.simulatorState?.account_summary?.initial_capital ?? 100000;
  }

  formatCurrency(n: number): string {
    if (Math.abs(n) >= 1e5) return '₹' + (n / 1e5).toFixed(2) + 'L';
    return '₹' + n.toFixed(0);
  }

  goToLogin(): void {
    this.demoService.exitDemo();
    this.router.navigate(['/login']);
  }

  goToDiscover(): void {
    this.router.navigate(['/discover']);
  }
}
