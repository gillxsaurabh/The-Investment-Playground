import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin.component.html',
  styleUrls: ['./admin.component.scss']
})
export class AdminComponent implements OnInit {
  isAdmin = false;
  checkingAdmin = true;

  // Admin broker token state
  brokerStatus: { active: boolean; valid: boolean } | null = null;
  brokerStatusLoading = false;

  // Kite linking flow
  kiteStep: 'idle' | 'fetching-url' | 'awaiting-token' | 'linking' | 'done' | 'error' = 'idle';
  kiteLoginUrl = '';
  requestToken = '';
  kiteError = '';

  // System stats
  stats: any = null;
  statsLoading = false;

  constructor(private http: HttpClient, private router: Router) {}

  ngOnInit(): void {
    // Check admin status fresh from server
    this.http.get<any>('/api/auth/me').subscribe({
      next: res => {
        this.checkingAdmin = false;
        if (res.success && res.user?.is_admin) {
          this.isAdmin = true;
          this.loadBrokerStatus();
          this.loadStats();
        } else {
          this.router.navigate(['/dashboard']);
        }
      },
      error: () => {
        this.checkingAdmin = false;
        this.router.navigate(['/dashboard']);
      }
    });
  }

  loadBrokerStatus(): void {
    this.brokerStatusLoading = true;
    this.http.get<any>('/api/admin/broker/status').subscribe({
      next: res => {
        this.brokerStatus = { active: res.active, valid: res.valid };
        this.brokerStatusLoading = false;
      },
      error: () => { this.brokerStatusLoading = false; }
    });
  }

  loadStats(): void {
    this.statsLoading = true;
    this.http.get<any>('/api/admin/dashboard').subscribe({
      next: res => { this.stats = res; this.statsLoading = false; },
      error: () => { this.statsLoading = false; }
    });
  }

  openKiteLogin(): void {
    this.kiteStep = 'fetching-url';
    this.http.get<any>('/api/admin/broker/login-url').subscribe({
      next: res => {
        this.kiteLoginUrl = res.login_url;
        window.open(res.login_url, '_blank');
        this.kiteStep = 'awaiting-token';
      },
      error: () => {
        this.kiteError = 'Failed to get login URL.';
        this.kiteStep = 'error';
      }
    });
  }

  linkAdminKite(): void {
    if (!this.requestToken.trim()) return;
    this.kiteStep = 'linking';
    this.http.post<any>('/api/admin/broker/link', { request_token: this.requestToken.trim() }).subscribe({
      next: res => {
        if (res.success) {
          this.kiteStep = 'done';
          this.loadBrokerStatus();
          this.loadStats();
        } else {
          this.kiteError = res.error || 'Linking failed.';
          this.kiteStep = 'error';
        }
      },
      error: () => {
        this.kiteError = 'Linking failed. Check the token and try again.';
        this.kiteStep = 'error';
      }
    });
  }

  resetKiteFlow(): void {
    this.kiteStep = 'idle';
    this.requestToken = '';
    this.kiteError = '';
  }
}
