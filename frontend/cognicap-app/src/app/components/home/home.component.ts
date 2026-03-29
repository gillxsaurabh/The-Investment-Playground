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
  @ViewChild('gearCanvas') gearCanvas!: ElementRef<HTMLCanvasElement>;

  /* ── Animation state ──────────────────────────────────────── */
  private particles: Particle[] = [];
  private heroRaf = 0;
  private gearRaf = 0;
  private gearTime = 0;
  private mouseX = -1000;
  private mouseY = -1000;
  private observer: IntersectionObserver | null = null;

  /* ── Nav scroll state ─────────────────────────────────────── */
  isScrolled = false;

  /* ── Logo secret tap ──────────────────────────────────────── */
  private logoClicks = 0;
  private logoTimer: ReturnType<typeof setTimeout> | null = null;

  /* ── Risk mode data ───────────────────────────────────────── */
  activeGear = 2;

  gears = [
    { name: 'Safe',     color: '#3b82f6', desc: 'Ultra-conservative. Only blue-chip Nifty 50 stocks with proven fundamentals and minimal volatility.', universe: 'Nifty 50',          riskPct: 15, speed: 0.3, amplitude: 0.35 },
    { name: 'Cautious', color: '#22c55e', desc: 'Quality large-caps from Nifty 100 with strong balance sheets and consistent earnings growth.', universe: 'Nifty 100',         riskPct: 35, speed: 0.5, amplitude: 0.5  },
    { name: 'Balanced', color: '#eab308', desc: 'Optimal risk-reward. Large and mid-caps from Nifty 500 with momentum and growth signals.', universe: 'Nifty 500',         riskPct: 55, speed: 0.8, amplitude: 0.7  },
    { name: 'Bold',     color: '#f97316', desc: 'Aggressive growth. Mid and small-caps with high momentum and sector rotation plays.', universe: 'Nifty 500 + Midcap', riskPct: 75, speed: 1.3, amplitude: 0.9  },
    { name: 'Turbo',    color: '#ef4444', desc: 'Maximum velocity. Full universe scan including small-caps. Highest risk, highest potential.', universe: '900+ Stocks',       riskPct: 95, speed: 2.2, amplitude: 1.2  },
  ];

  agents = [
    { name: 'Fundamental Agent',    icon: 'account_balance', color: '#22c55e', desc: 'Deep-dives into balance sheets, ROE, debt-to-equity ratios, and quarterly profit trends from Screener.in.' },
    { name: 'Technical Agent',      icon: 'show_chart',      color: '#6c63ff', desc: 'Charts RSI, ADX, EMA crossovers, ATR volatility, and 3-month relative strength versus Nifty and sector.' },
    { name: 'News Sentiment Agent', icon: 'newspaper',       color: '#eab308', desc: 'Scrapes real-time headlines from Google News and analyses sentiment to detect breaking events and shifts.' },
    { name: 'Sector Scanner',       icon: 'pie_chart',       color: '#f97316', desc: 'Monitors 20+ sector indices for rotation patterns, 5-day momentum, and relative strength vs the broad market.' },
  ];

  constructor(
    private router: Router,
    private demoService: DemoService,
    private ngZone: NgZone,
    private el: ElementRef,
  ) {}

  /* ── Lifecycle ────────────────────────────────────────────── */

  ngAfterViewInit(): void {
    this.ngZone.runOutsideAngular(() => {
      this.initHeroCanvas();
      this.initGearCanvas();
      window.addEventListener('resize', this.onResize);
      window.addEventListener('mousemove', this.onMouseMove);
      window.addEventListener('scroll', this.onScroll, { passive: true });
    });
    setTimeout(() => this.initScrollReveal(), 120);
  }

  ngOnDestroy(): void {
    cancelAnimationFrame(this.heroRaf);
    cancelAnimationFrame(this.gearRaf);
    this.observer?.disconnect();
    window.removeEventListener('resize', this.onResize);
    window.removeEventListener('mousemove', this.onMouseMove);
    window.removeEventListener('scroll', this.onScroll);
  }

  /* ── Hero Canvas — particle network ───────────────────────── */

  private onResize = (): void => {
    const c = this.heroCanvas?.nativeElement;
    if (c) { c.width = window.innerWidth; c.height = window.innerHeight; this.createParticles(c.width, c.height); }
    const g = this.gearCanvas?.nativeElement;
    if (g?.parentElement) { const r = g.parentElement.getBoundingClientRect(); g.width = r.width; g.height = r.height; }
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

    // Connections
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

    // Dots
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

  /* ── Gear Chart Canvas ────────────────────────────────────── */

  private initGearCanvas(): void {
    const c = this.gearCanvas?.nativeElement;
    if (!c?.parentElement) return;
    const r = c.parentElement.getBoundingClientRect();
    c.width = r.width || 500;
    c.height = r.height || 180;
    this.animateGear();
  }

  private animateGear(): void {
    const c = this.gearCanvas?.nativeElement;
    if (!c) return;
    const ctx = c.getContext('2d')!;
    const { width: w, height: h } = c;
    const gear = this.gears[this.activeGear];
    this.gearTime += 0.015;
    ctx.clearRect(0, 0, w, h);

    const mid = h * 0.45;
    ctx.beginPath();
    ctx.moveTo(0, mid);
    for (let x = 0; x < w; x++) {
      const t = this.gearTime;
      const y = mid
        + Math.sin((x * 0.018 + t * 2) * gear.speed) * (h * 0.15 * gear.amplitude)
        + Math.sin((x * 0.008 + t * 1.3) * gear.speed) * (h * 0.08 * gear.amplitude)
        + Math.cos((x * 0.025 + t * 0.8) * gear.speed) * (h * 0.05 * gear.amplitude);
      ctx.lineTo(x, y);
    }
    ctx.strokeStyle = gear.color;
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, gear.color + '18');
    grad.addColorStop(1, 'transparent');
    ctx.fillStyle = grad;
    ctx.fill();

    this.gearRaf = requestAnimationFrame(() => this.animateGear());
  }

  /* ── Scroll Reveal ────────────────────────────────────────── */

  private initScrollReveal(): void {
    this.observer = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) e.target.classList.add('visible'); }),
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' },
    );
    this.el.nativeElement.querySelectorAll('.reveal').forEach((el: Element) => this.observer!.observe(el));
  }

  /* ── Public actions ───────────────────────────────────────── */

  selectGear(i: number): void { this.activeGear = i; }

  scrollTo(id: string): void {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  }

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
