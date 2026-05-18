import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule, DecimalPipe],
  templateUrl: './admin.component.html',
  styleUrls: ['./admin.component.scss']
})
export class AdminComponent implements OnInit, OnDestroy {
  bootstrapping = false;
  bootstrapMsg = '';

  // Admin broker token state
  brokerStatus: { active: boolean; valid: boolean } | null = null;
  brokerStatusLoading = false;
  brokerStatusError = '';
  statsError = '';
  whoami: any = null;

  // Kite linking flow
  kiteStep: 'idle' | 'fetching-url' | 'awaiting-token' | 'linking' | 'done' | 'error' = 'idle';
  kiteLoginUrl = '';
  requestToken = '';
  kiteError = '';

  // System stats
  stats: any = null;
  statsLoading = false;

  // LLM usage
  llmUsage: any[] = [];
  llmUsageLoading = false;
  llmTotalCost = 0;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.loadWhoami();
    this.loadBrokerStatus();
    this.loadStats();
    this.loadLlmUsage();
  }

  loadLlmUsage(): void {
    this.llmUsageLoading = true;
    this.http.get<any>('/api/admin/llm-usage').subscribe({
      next: res => {
        this.llmUsage = res.usage || [];
        this.llmTotalCost = this.llmUsage.reduce((sum: number, r: any) => sum + (r.total_cost_usd || 0), 0);
        this.llmUsageLoading = false;
      },
      error: () => { this.llmUsageLoading = false; }
    });
  }

  loadWhoami(): void {
    this.http.get<any>('/api/admin/whoami').subscribe({
      next: res => { this.whoami = res; },
      error: () => {}
    });
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
      error: (err) => {
        const msg = err?.error?.error;
        if (err?.status === 403) {
          this.kiteError = 'Access denied — you must be admin to link the global token.';
        } else if (msg) {
          this.kiteError = msg;
        } else {
          this.kiteError = 'Linking failed. Check the Railway logs for details.';
        }
        this.kiteStep = 'error';
      }
    });
  }

  bootstrapAdmin(): void {
    this.bootstrapping = true;
    this.bootstrapMsg = '';
    this.http.post<any>('/api/admin/bootstrap', {}).subscribe({
      next: res => {
        this.bootstrapMsg = res.message || 'Done';
        this.bootstrapping = false;
        this.loadWhoami();
        this.loadBrokerStatus();
        this.loadStats();
      },
      error: (err) => {
        this.bootstrapMsg = err?.error?.error || 'Bootstrap failed.';
        this.bootstrapping = false;
      }
    });
  }

  resetKiteFlow(): void {
    this.kiteStep = 'idle';
    this.requestToken = '';
    this.kiteError = '';
  }

  // ── Retrospective Analysis ──────────────────────────────────────────────
  retroMode: 'simulator' | 'live' = 'simulator';
  retroLookback: number = 90;
  retroRunning = false;
  retroStages: { stage: string; label: string; status: 'pending' | 'running' | 'done' | 'error' }[] = [];
  retroLogs: string[] = [];
  retroError = '';
  retroReports: any[] = [];
  retroReportsLoading = false;
  retroSelectedReport: any = null;
  retroSelectedReportLoading = false;
  private _retroSse: EventSource | null = null;

  readonly RETRO_STAGE_LABELS: Record<string, string> = {
    pipeline: 'Pipeline',
    data_fetch: 'Data Fetch',
    cohort_builder: 'Cohort Builder',
    winner_patterns: 'Winner Pattern Hunter',
    loser_patterns: 'Loser Pattern Hunter',
    filter_audit: 'Filter Rejection Auditor',
    sl_calibration: 'Stop-Loss Calibrator',
    conviction_calibration: 'Conviction Calibrator',
    sell_audit_calibration: 'Sell-Audit Calibrator',
    synthesizer: 'Synthesizer (Opus 4.7)',
  };

  ngOnDestroy(): void {
    this._retroSse?.close();
  }

  loadRetroReports(): void {
    this.retroReportsLoading = true;
    this.http.get<any>(`/api/retrospective/reports?mode=${this.retroMode}`).subscribe({
      next: res => { this.retroReports = res.reports || []; this.retroReportsLoading = false; },
      error: () => { this.retroReportsLoading = false; }
    });
  }

  runRetrospective(): void {
    if (this.retroRunning) return;
    this.retroRunning = true;
    this.retroError = '';
    this.retroLogs = [];
    this.retroStages = Object.entries(this.RETRO_STAGE_LABELS).map(([stage, label]) => ({
      stage, label, status: 'pending' as const
    }));

    this._retroSse?.close();

    // POST then SSE via EventSource workaround: trigger via fetch first, then open SSE
    // Since EventSource doesn't support POST, we use fetch with streaming
    const body = JSON.stringify({ trading_mode: this.retroMode, lookback_days: this.retroLookback });
    fetch('/api/retrospective/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('jwt_access_token')}` },
      body,
    }).then(resp => {
      if (!resp.ok) { this.retroError = `Server error: ${resp.status}`; this.retroRunning = false; return; }
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const pump = (): Promise<void> => reader.read().then(({ done, value }) => {
        if (done) { this.retroRunning = false; this.loadRetroReports(); return; }
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';
        for (const part of parts) {
          const eventLine = part.match(/^event: (.+)$/m)?.[1];
          const dataLine = part.match(/^data: (.+)$/m)?.[1];
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine);
            if (eventLine === 'step_start') {
              const s = this.retroStages.find(x => x.stage === payload.step);
              if (s) s.status = 'running';
            } else if (eventLine === 'step_complete') {
              const s = this.retroStages.find(x => x.stage === payload.step);
              if (s) s.status = 'done';
            } else if (eventLine === 'step_log') {
              this.retroLogs.push(`[${payload.step}] ${payload.message}`);
              if (this.retroLogs.length > 50) this.retroLogs.shift();
            } else if (eventLine === 'error') {
              this.retroError = payload.message;
              this.retroRunning = false;
            } else if (eventLine === 'final_result') {
              this.retroStages.forEach(s => { if (s.status !== 'error') s.status = 'done'; });
            }
          } catch {}
        }
        return pump();
      });
      pump().catch(e => { this.retroError = String(e); this.retroRunning = false; });
    }).catch(e => { this.retroError = String(e); this.retroRunning = false; });
  }

  viewReport(reportId: string): void {
    this.retroSelectedReportLoading = true;
    this.retroSelectedReport = null;
    this.http.get<any>(`/api/retrospective/reports/${reportId}`).subscribe({
      next: res => { this.retroSelectedReport = res.report; this.retroSelectedReportLoading = false; },
      error: () => { this.retroSelectedReportLoading = false; }
    });
  }

  closeReport(): void {
    this.retroSelectedReport = null;
  }

  getPnlClass(pnl: number | null): string {
    if (pnl == null) return '';
    return pnl > 0 ? 'green-text' : pnl < 0 ? 'red-text' : '';
  }

  getConfidenceBadgeClass(c: string): string {
    if (c === 'high') return 'conf-high';
    if (c === 'medium') return 'conf-medium';
    return 'conf-low';
  }
}
