import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService, User } from '../../services/auth.service';
import { HeaderBannerComponent } from '../shared/header-banner/header-banner.component';
import { KiteService, MarketIndex, Stock } from '../../services/kite.service';
import { SimulatorService, AutomationStatus, AutomationRunRecord } from '../../services/simulator.service';
import { forkJoin, interval, Subscription } from 'rxjs';

@Component({
  selector: 'app-account',
  standalone: true,
  imports: [CommonModule, FormsModule, HeaderBannerComponent],
  templateUrl: './account.component.html',
  styleUrls: ['./account.component.scss']
})
export class AccountComponent implements OnInit, OnDestroy {
  activeTab: 'profile' | 'broker' | 'security' | 'automation' = 'profile';

  user: User | null = null;
  brokerLinked = false;
  brokerInfo: { broker_user_id: string; broker_user_name: string; linked_at: string } | null = null;

  // Broker linking flow
  kiteLoginUrl: string | null = null;
  requestToken = '';
  linkStatus: 'idle' | 'loading' | 'success' | 'error' = 'idle';
  linkError = '';

  // Broker status check
  brokerStatusChecking = false;
  brokerStatusMsg = '';

  // Change password
  currentPassword = '';
  newPassword = '';
  confirmNewPassword = '';
  passwordChangeStatus: 'idle' | 'loading' | 'success' | 'error' = 'idle';
  passwordChangeError = '';
  passwordChangeSuccess = '';

  // Automation
  automationStatus: AutomationStatus | null = null;
  automationHistory: AutomationRunRecord[] = [];
  isLoadingStatus = false;
  isLoadingHistory = false;
  isRunning = false;
  runResult: AutomationRunRecord | null = null;
  runError = '';
  automationMode: 'simulator' | 'live' = 'simulator';
  isDryRun = true;
  private automationLoaded = false;
  private statusRefreshSub: Subscription | null = null;

  readonly GEAR_LABELS: Record<number, string> = {
    1: 'Fortress', 2: 'Cautious', 3: 'Balanced', 4: 'Growth', 5: 'Turbo'
  };

  // Market data for header banner
  nifty: MarketIndex | null = null;
  sensex: MarketIndex | null = null;
  marketGainers: Stock[] = [];
  marketLosers: Stock[] = [];
  isMarketLoading = true;
  marketError = '';
  private marketRefreshSub: Subscription | null = null;

  constructor(
    private authService: AuthService,
    private kiteService: KiteService,
    private simulatorService: SimulatorService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.authService.user$.subscribe(u => { this.user = u; });
    this.authService.brokerLinked$.subscribe(linked => { this.brokerLinked = linked; });
    this.loadMarketData();
    this.marketRefreshSub = interval(30000).subscribe(() => this.loadMarketData());
    this.fetchBrokerInfo();
  }

  ngOnDestroy(): void {
    this.marketRefreshSub?.unsubscribe();
    this.statusRefreshSub?.unsubscribe();
  }

  selectTab(tab: 'profile' | 'broker' | 'security' | 'automation'): void {
    this.activeTab = tab;
    if (tab === 'automation' && !this.automationLoaded) {
      this.loadAutomationStatus();
      this.loadAutomationHistory();
      this.automationLoaded = true;
      this.statusRefreshSub = interval(60000).subscribe(() => this.loadAutomationStatus());
    }
  }

  private fetchBrokerInfo(): void {
    this.authService.fetchMe().subscribe({
      next: res => {
        if (res.success) {
          this.brokerInfo = res.broker ?? null;
          this.brokerLinked = res.broker_linked ?? false;
        }
      },
      error: () => {}
    });
  }

  loadMarketData(): void {
    forkJoin({
      indices: this.kiteService.getMarketIndices(),
      stocks: this.kiteService.getTopStocks()
    }).subscribe({
      next: results => {
        if (results.indices.success) {
          this.nifty = results.indices.nifty ?? null;
          this.sensex = results.indices.sensex ?? null;
        }
        if (results.stocks.success) {
          this.marketGainers = results.stocks.top_gainers ?? [];
          this.marketLosers = results.stocks.top_losers ?? [];
        }
        this.isMarketLoading = false;
      },
      error: () => {
        this.isMarketLoading = false;
        this.marketError = 'Failed to load market data.';
      }
    });
  }

  getKiteLoginUrl(): void {
    this.authService.getBrokerLoginUrl().subscribe({
      next: res => {
        if (res.success && res.login_url) {
          this.kiteLoginUrl = res.login_url;
          window.open(res.login_url, '_blank');
        }
      },
      error: () => {}
    });
  }

  linkBroker(): void {
    if (!this.requestToken.trim()) return;
    this.linkStatus = 'loading';
    this.linkError = '';
    this.authService.linkBroker(this.requestToken.trim()).subscribe({
      next: res => {
        if (res.success) {
          this.linkStatus = 'success';
          this.requestToken = '';
          this.kiteLoginUrl = null;
          this.fetchBrokerInfo();
        } else {
          this.linkStatus = 'error';
          this.linkError = res.error || 'Failed to link broker account.';
        }
      },
      error: err => {
        this.linkStatus = 'error';
        this.linkError = err?.error?.error || 'Failed to link broker account.';
      }
    });
  }

  checkBrokerStatus(): void {
    this.brokerStatusChecking = true;
    this.brokerStatusMsg = '';
    this.authService.getBrokerStatus().subscribe({
      next: (res: any) => {
        this.brokerStatusChecking = false;
        this.brokerStatusMsg = res.valid
          ? 'Kite session is active and valid.'
          : 'Kite session has expired. Re-link to continue.';
        if (!res.valid) {
          this.brokerLinked = false;
          localStorage.setItem('broker_linked', 'false');
        }
      },
      error: () => {
        this.brokerStatusChecking = false;
        this.brokerStatusMsg = 'Could not check broker status.';
      }
    });
  }

  changePassword(): void {
    if (!this.currentPassword) { this.passwordChangeError = 'Current password is required'; return; }
    if (this.newPassword.length < 8) { this.passwordChangeError = 'New password must be at least 8 characters'; return; }
    if (this.newPassword !== this.confirmNewPassword) { this.passwordChangeError = 'Passwords do not match'; return; }

    this.passwordChangeStatus = 'loading';
    this.passwordChangeError = '';
    this.passwordChangeSuccess = '';

    this.authService.changePassword(this.currentPassword, this.newPassword).subscribe({
      next: (res: any) => {
        if (res.success) {
          this.passwordChangeStatus = 'success';
          this.passwordChangeSuccess = 'Password changed. You will be logged out.';
          this.currentPassword = '';
          this.newPassword = '';
          this.confirmNewPassword = '';
          setTimeout(() => this.authService.logout(), 2000);
        } else {
          this.passwordChangeStatus = 'error';
          this.passwordChangeError = res.error || 'Failed to change password.';
        }
      },
      error: (err: any) => {
        this.passwordChangeStatus = 'error';
        this.passwordChangeError = err.error?.error || 'Failed to change password.';
      }
    });
  }

  // ── Automation ────────────────────────────────────────────────

  loadAutomationStatus(): void {
    this.isLoadingStatus = true;
    this.simulatorService.getAutomationStatus().subscribe({
      next: (status) => {
        this.automationStatus = status;
        this.automationMode = status.mode ?? 'simulator';
        this.isLoadingStatus = false;
      },
      error: () => { this.isLoadingStatus = false; }
    });
  }

  loadAutomationHistory(): void {
    this.isLoadingHistory = true;
    this.simulatorService.getAutomationHistory().subscribe({
      next: (res) => {
        this.automationHistory = res.history ?? [];
        this.isLoadingHistory = false;
      },
      error: () => { this.isLoadingHistory = false; }
    });
  }

  toggleAutomation(): void {
    if (!this.automationStatus) return;
    const enabling = !this.automationStatus.enabled;
    this.simulatorService.enableAutomation(enabling, this.automationMode).subscribe({
      next: () => { this.loadAutomationStatus(); },
      error: () => {}
    });
  }

  runNow(): void {
    if (this.isRunning) return;
    this.isRunning = true;
    this.runResult = null;
    this.runError = '';
    this.simulatorService.runAutomationNow(this.isDryRun).subscribe({
      next: (res: any) => {
        this.isRunning = false;
        this.runResult = res.run_record ?? res;
        this.loadAutomationStatus();
        this.loadAutomationHistory();
      },
      error: (err: any) => {
        this.isRunning = false;
        this.runError = err.error?.error || 'Run failed. Check server logs.';
      }
    });
  }

  getStatusLabel(run: AutomationRunRecord): string {
    const map: Record<string, string> = { completed: 'Completed', skipped: 'Skipped', error: 'Error', dry_run: 'Dry Run' };
    return map[run.status] ?? run.status;
  }

  getStatusClass(run: AutomationRunRecord): string {
    const map: Record<string, string> = { completed: 'status-ok', skipped: 'status-skip', error: 'status-err', dry_run: 'status-dry' };
    return map[run.status] ?? '';
  }

  formatDate(dt: string): string {
    if (!dt) return '—';
    return new Date(dt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  logout(): void {
    this.authService.logout();
  }
}
