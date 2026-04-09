import {
  Component,
  AfterViewInit,
  OnDestroy,
  ElementRef,
  ViewChild,
  NgZone,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { DemoService } from '../../services/demo.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss'],
})
export class HomeComponent implements AfterViewInit, OnDestroy {
  @ViewChild('splashVideo') splashVideo!: ElementRef<HTMLVideoElement>;

  private splashTimeout: ReturnType<typeof setTimeout> | null = null;

  showSplash = true;
  splashFading = false;

  isScrolled = false;

  private logoClicks = 0;
  private logoTimer: ReturnType<typeof setTimeout> | null = null;

  /* ── Slide carousel ─────────────────────────────────────────── */
  activeSlide = 0;
  private slideInterval: ReturnType<typeof setInterval> | null = null;

  slides = [
    {
      badge: 'SEAMLESS INTEGRATION',
      title: 'Plug &',
      highlight: 'Play.',
      desc: 'Connect your Kite account in seconds via secure API. Instantly view your portfolio\'s health, positions, and P&L.',
      visual: 'integration',
    },
    {
      badge: 'THE AGENT ECOSYSTEM',
      title: 'Your AI',
      highlight: 'Analyst Army.',
      desc: 'Six specialist AI agents scan, analyse, and score every stock across market conditions, technicals, fundamentals, news, sector dynamics, and conviction — then rank and execute.',
      visual: 'agents',
    },
    {
      badge: 'AUTOMATE & PROTECT',
      title: 'Full Control.',
      highlight: 'Full Automation.',
      desc: 'Every Monday at 9 AM, the system runs the full pipeline — scanning, filtering, ranking, and executing trades automatically.',
      visual: 'execution',
    },
    {
      badge: 'PERSONALIZED RISK',
      title: 'Choose Your',
      highlight: 'Risk Profile.',
      desc: 'Five calibrated risk modes from blue-chip safety to full-universe hunting — you decide how aggressive the AI trades.',
      visual: 'gears',
    },
    {
      badge: 'ZERO-RISK SANDBOX',
      title: 'Switch to ',
      highlight: 'Simulator mode.',
      desc: 'First test in theory then invest.',
      visual: 'simulator',
    },
  ];

  agents = [
    { name: 'Market Scanner',    icon: 'radar',           color: '#d4a843' },
    { name: 'Quant Analyst',     icon: 'show_chart',      color: '#5b8def' },
    { name: 'Fundamentals',      icon: 'account_balance', color: '#00c176' },
    { name: 'Sector Momentum',   icon: 'pie_chart',       color: '#f97316' },
    { name: 'AI Conviction',     icon: 'psychology',      color: '#d4a843' },
    { name: 'Portfolio Analyst', icon: 'analytics',       color: '#5b8def' },
  ];

  gears = [
    { name: 'Safe',     color: '#3b82f6', pct: 20  },
    { name: 'Cautious', color: '#22c55e', pct: 40  },
    { name: 'Balanced', color: '#eab308', pct: 60  },
    { name: 'Bold',     color: '#f97316', pct: 80  },
    { name: 'Turbo',    color: '#ef4444', pct: 100 },
  ];

  constructor(
    private router: Router,
    private demoService: DemoService,
    private ngZone: NgZone,
  ) {}

  /* ── Lifecycle ──────────────────────────────────────────────── */

  ngAfterViewInit(): void {
    const video = this.splashVideo.nativeElement;
    video.muted = true;
    video.play().catch(() => {});

    this.splashTimeout = setTimeout(() => this.onSplashEnd(), 6000);

    this.ngZone.runOutsideAngular(() => {
      window.addEventListener('scroll', this.onScroll, { passive: true });
    });
    this.startSlideshow();
  }

  ngOnDestroy(): void {
    this.stopSlideshow();
    if (this.splashTimeout) clearTimeout(this.splashTimeout);
    window.removeEventListener('scroll', this.onScroll);
  }

  private onScroll = (): void => {
    const scrolled = window.scrollY > 60;
    if (scrolled !== this.isScrolled) {
      this.ngZone.run(() => { this.isScrolled = scrolled; });
    }
  };

  /* ── Slideshow (auto-advances every 3.5s, resets on manual click) ── */

  private startSlideshow(): void {
    this.stopSlideshow();
    this.slideInterval = setInterval(() => {
      this.ngZone.run(() => {
        this.activeSlide = (this.activeSlide + 1) % this.slides.length;
      });
    }, 3500);
  }

  private stopSlideshow(): void {
    if (this.slideInterval) {
      clearInterval(this.slideInterval);
      this.slideInterval = null;
    }
  }

  goToSlide(i: number): void {
    this.activeSlide = i;
    this.startSlideshow(); // reset timer on manual click
  }

  /* ── Splash ─────────────────────────────────────────────────── */

  onSplashEnd(): void {
    if (this.splashFading) return;          // already dismissing
    if (this.splashTimeout) { clearTimeout(this.splashTimeout); this.splashTimeout = null; }
    this.splashFading = true;
    setTimeout(() => { this.showSplash = false; }, 600);
  }

  /* ── Public actions ─────────────────────────────────────────── */

  enterDemo(): void {
    this.demoService.enterDemo();
    this.router.navigate(['/dashboard']);
  }

  goToSignup(): void { this.router.navigate(['/login']); }
  goToLogin(): void  { this.router.navigate(['/login']); }

  onLogoClick(): void {
    this.logoClicks++;
    if (this.logoTimer) clearTimeout(this.logoTimer);
    if (this.logoClicks >= 5) { this.logoClicks = 0; this.router.navigate(['/login']); return; }
    this.logoTimer = setTimeout(() => { this.logoClicks = 0; }, 3000);
  }

  openDevLogin(): void { this.router.navigate(['/login']); }
}
