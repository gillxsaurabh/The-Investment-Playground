import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin.component.html',
  styleUrls: ['./admin.component.scss']
})
export class AdminComponent implements OnInit {
  // Admin broker token state
  brokerStatus: { active: boolean; valid: boolean } | null = null;
  brokerStatusLoading = false;
  brokerStatusError = '';
  statsError = '';

  // Kite linking flow
  kiteStep: 'idle' | 'fetching-url' | 'awaiting-token' | 'linking' | 'done' | 'error' = 'idle';
  kiteLoginUrl = '';
  requestToken = '';
  kiteError = '';

  // System stats
  stats: any = null;
  statsLoading = false;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.loadBrokerStatus();
    this.loadStats();
  }

  loadBrokerStatus(): void {
    this.brokerStatusLoading = true;
    this.brokerStatusError = '';
    this.http.get<any>('/api/admin/broker/status').subscribe({
      next: res => {
        this.brokerStatus = { active: res.active, valid: res.valid };
        this.brokerStatusLoading = false;
      },
      error: (err) => {
        this.brokerStatusLoading = false;
        if (err?.status === 403) {
          this.brokerStatusError = 'Access denied — ADMIN_EMAIL may not match your account email.';
        }
      }
    });
  }

  loadStats(): void {
    this.statsLoading = true;
    this.statsError = '';
    this.http.get<any>('/api/admin/dashboard').subscribe({
      next: res => { this.stats = res; this.statsLoading = false; },
      error: (err) => {
        this.statsLoading = false;
        if (err?.status === 403) {
          this.statsError = 'Access denied — ADMIN_EMAIL may not match your account email.';
        }
      }
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
      error: (err) => {
        if (err?.status === 403) {
          this.kiteError = 'Access denied. Your account is not recognized as admin. Check that ADMIN_EMAIL matches your login email on Railway.';
        } else {
          this.kiteError = 'Failed to get login URL. Check that KITE_API_KEY and KITE_API_SECRET are set in Railway environment variables.';
        }
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
