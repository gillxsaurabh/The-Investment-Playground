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

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  opacity: number;
}

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss'],
})
export class HomeComponent implements AfterViewInit, OnDestroy {
  @ViewChild('heroCanvas') heroCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('splashVideo') splashVideo!: ElementRef<HTMLVideoElement>;

  private particles: Particle[] = [];
  private heroRaf = 0;
  private mouseX = -1000;
  private mouseY = -1000;
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
      title: 'Test Theories.',
      highlight: 'Risk Nothing.',
      desc: 'Run the full AI pipeline with \u20B95,00,000 virtual capital before committing real money.',
      visual: 'simulator',
    },
  ];

  agents = [
    { name: 'Market Scanner',    icon: 'radar',           color: '#3b82f6' },
    { name: 'Quant Analyst',     icon: 'show_chart',      color: '#6c63ff' },
    { name: 'Fundamentals',      icon: 'account_balance', color: '#22c55e' },
    { name: 'Sector Momentum',   icon: 'pie_chart',       color: '#f97316' },
    { name: 'AI Conviction',     icon: 'psychology',      color: '#06b6d4' },
    { name: 'Portfolio Analyst', icon: 'analytics',       color: '#ec4899' },
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
    // Programmatically mute + play (Angular doesn't reliably apply the muted attribute)
    const video = this.splashVideo.nativeElement;
    video.muted = true;
    video.play().catch(() => {
      // Play failed (e.g. policy block) — fall through to safety timeout
    });

    // Safety: dismiss splash after 6s even if video never fires ended
    this.splashTimeout = setTimeout(() => this.onSplashEnd(), 6000);

    this.ngZone.runOutsideAngular(() => {
      this.initHeroCanvas();
      window.addEventListener('resize', this.onResize);
      window.addEventListener('mousemove', this.onMouseMove);
      window.addEventListener('scroll', this.onScroll, { passive: true });
    });
    this.startSlideshow();
  }

  ngOnDestroy(): void {
    cancelAnimationFrame(this.heroRaf);
    this.stopSlideshow();
    if (this.splashTimeout) clearTimeout(this.splashTimeout);
    window.removeEventListener('resize', this.onResize);
    window.removeEventListener('mousemove', this.onMouseMove);
    window.removeEventListener('scroll', this.onScroll);
  }

  /* ── Hero Canvas — particle network ─────────────────────────── */

  private onResize = (): void => {
    const c = this.heroCanvas?.nativeElement;
    if (c) {
      c.width = window.innerWidth;
      c.height = window.innerHeight;
      this.createParticles(c.width, c.height);
    }
  };

  private onMouseMove = (e: MouseEvent): void => {
    this.mouseX = e.clientX;
    this.mouseY = e.clientY;
  };

  private onScroll = (): void => {
    const scrolled = window.scrollY > 60;
    if (scrolled !== this.isScrolled) {
      this.ngZone.run(() => { this.isScrolled = scrolled; });
    }
  };

  private initHeroCanvas(): void {
    const canvas = this.heroCanvas.nativeElement;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    this.createParticles(canvas.width, canvas.height);
    this.animateHero();
  }

  private createParticles(w: number, h: number): void {
    const count = Math.min(80, Math.max(20, Math.floor(w / 25)));
    this.particles = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      radius: Math.random() * 1.5 + 0.8,
      opacity: Math.random() * 0.4 + 0.15,
    }));
  }

  private animateHero(): void {
    const canvas = this.heroCanvas.nativeElement;
    const ctx = canvas.getContext('2d')!;
    const w = canvas.width;
    const h = canvas.height;
    const maxDist = 140;

    ctx.clearRect(0, 0, w, h);

    for (const p of this.particles) {
      const dx = p.x - this.mouseX;
      const dy = p.y - this.mouseY;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 120 && dist > 0) {
        const force = (120 - dist) / 120 * 0.4;
        p.vx += (dx / dist) * force * 0.08;
        p.vy += (dy / dist) * force * 0.08;
      }
      p.vx *= 0.99;
      p.vy *= 0.99;
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) { p.x = 0; p.vx *= -1; }
      if (p.x > w) { p.x = w; p.vx *= -1; }
      if (p.y < 0) { p.y = 0; p.vy *= -1; }
      if (p.y > h) { p.y = h; p.vy *= -1; }
    }

    for (let i = 0; i < this.particles.length; i++) {
      for (let j = i + 1; j < this.particles.length; j++) {
        const a = this.particles[i], b = this.particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < maxDist) {
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = `rgba(108,99,255,${(1 - dist / maxDist) * 0.12})`;
          ctx.lineWidth = 0.6;
          ctx.stroke();
        }
      }
    }

    for (const p of this.particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius * 4, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(108,99,255,${p.opacity * 0.08})`;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(108,99,255,${p.opacity})`;
      ctx.fill();
    }

    this.heroRaf = requestAnimationFrame(() => this.animateHero());
  }

  /* ── Slideshow ──────────────────────────────────────────────── */

  private startSlideshow(): void {
    this.slideInterval = setInterval(() => {
      this.ngZone.run(() => {
        this.activeSlide = (this.activeSlide + 1) % this.slides.length;
      });
    }, 3000);
  }

  private stopSlideshow(): void {
    if (this.slideInterval) {
      clearInterval(this.slideInterval);
      this.slideInterval = null;
    }
  }

  goToSlide(i: number): void {
    this.activeSlide = i;
    this.stopSlideshow();
    this.startSlideshow();
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
