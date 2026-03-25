import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { DemoService } from './services/demo.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet],
  template: `
    <router-outlet></router-outlet>

    <!-- Kite sign-in prompt (demo mode) -->
    <div class="kite-prompt-overlay" *ngIf="showPrompt" (click)="dismiss()">
      <div class="kite-prompt-card" (click)="$event.stopPropagation()">
        <div class="kp-icon">
          <svg width="26" height="26" fill="none" viewBox="0 0 24 24">
            <rect x="3" y="11" width="18" height="11" rx="2" stroke="#6c63ff" stroke-width="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4" stroke="#6c63ff" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
        <h3 class="kp-title">Live data required</h3>
        <p class="kp-body">
          This feature connects to your live Zerodha portfolio and places real or paper trades.
          Sign in with your Kite account to unlock it.
        </p>
        <div class="kp-actions">
          <button class="kp-btn-primary" (click)="goToLogin()">Connect Kite Account</button>
          <button class="kp-btn-ghost" (click)="dismiss()">Continue in Demo</button>
        </div>
        <div class="kp-note">
          <svg width="12" height="12" fill="none" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
            <path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          You're in demo mode — all portfolio and position data shown is for illustration only.
        </div>
      </div>
    </div>
  `,
  styles: [`
    .kite-prompt-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(6px);
      z-index: 9999;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
      animation: fadeIn 0.2s ease;
    }

    @keyframes fadeIn {
      from { opacity: 0; }
      to   { opacity: 1; }
    }

    .kite-prompt-card {
      background: #12121e;
      border: 1px solid rgba(108, 99, 255, 0.25);
      border-radius: 20px;
      padding: 2rem;
      max-width: 420px;
      width: 100%;
      text-align: center;
      animation: slideUp 0.25s ease;
    }

    @keyframes slideUp {
      from { transform: translateY(20px); opacity: 0; }
      to   { transform: translateY(0);    opacity: 1; }
    }

    .kp-icon {
      width: 56px;
      height: 56px;
      background: rgba(108, 99, 255, 0.1);
      border: 1px solid rgba(108, 99, 255, 0.25);
      border-radius: 16px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 1.2rem;
    }

    .kp-title {
      font-size: 1.15rem;
      font-weight: 700;
      color: #e8e8f0;
      margin: 0 0 0.6rem;
    }

    .kp-body {
      font-size: 0.88rem;
      color: #7777a0;
      line-height: 1.6;
      margin: 0 0 1.5rem;
    }

    .kp-actions {
      display: flex;
      flex-direction: column;
      gap: 0.7rem;
      margin-bottom: 1.2rem;
    }

    .kp-btn-primary {
      padding: 0.8rem 1.5rem;
      border-radius: 10px;
      border: none;
      background: linear-gradient(135deg, #6c63ff, #00d4aa);
      color: #fff;
      font-size: 0.9rem;
      font-weight: 700;
      cursor: pointer;
      transition: opacity 0.2s;

      &:hover { opacity: 0.9; }
    }

    .kp-btn-ghost {
      padding: 0.8rem 1.5rem;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.08);
      background: transparent;
      color: #7777a0;
      font-size: 0.88rem;
      cursor: pointer;
      transition: border-color 0.2s, color 0.2s;

      &:hover { border-color: rgba(255,255,255,0.2); color: #e8e8f0; }
    }

    .kp-note {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.4rem;
      font-size: 0.72rem;
      color: #44445a;
    }
  `]
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'TIP';
  showPrompt = false;
  private sub: Subscription | null = null;

  constructor(private demoService: DemoService, private router: Router) {}

  ngOnInit(): void {
    this.sub = this.demoService.showPrompt$.subscribe(v => (this.showPrompt = v));
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  dismiss(): void {
    this.demoService.hideKitePrompt();
  }

  goToLogin(): void {
    this.demoService.hideKitePrompt();
    this.router.navigate(['/login']);
  }
}
