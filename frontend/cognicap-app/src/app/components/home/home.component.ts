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

  openFaq: number | null = null;

  faqs = [
    {
      q: 'Is my data secure?',
      a: 'We use read-only API access to your broker account. We never store your credentials — only an access token that expires every day. Your portfolio data stays on our servers encrypted at rest.',
    },
    {
      q: 'Will the AI auto-execute trades?',
      a: 'Only if you explicitly enable it with safety rules. By default, every trade needs your approval. StockCraft is a research platform — the agents do the work, you pull the trigger.',
    },
    {
      q: 'How is StockCraft different from Smallcase?',
      a: 'Smallcase sells pre-built portfolios. StockCraft is a research workspace — you decide what to buy. We don\'t sell baskets. Our AI agents analyse your specific holdings and the market in real time.',
    },
    {
      q: 'How is StockCraft different from Tickertape?',
      a: 'Tickertape gives you static screeners and data tables. StockCraft gives you an AI research team that converses, explains, and connects the dots across your actual portfolio — personalised, not generic.',
    },
    {
      q: 'Is StockCraft SEBI registered?',
      a: 'StockCraft is an AI-powered research and analytics platform. We are not a SEBI-registered investment adviser and do not provide personalised investment advice. Our agents provide research; all investment decisions are yours.',
    },
    {
      q: 'What does it cost?',
      a: 'Free if you bring your own LLM API key (Claude, OpenAI, or Gemini). Managed plan at ₹999/month includes StockCraft-managed Claude Sonnet with priority support and higher rate limits.',
    },
    {
      q: 'Can I use StockCraft with my SIP?',
      a: 'Yes — connect any supported broker and your SIP holdings appear in your portfolio analysis automatically. The agents treat them like any other holding.',
    },
    {
      q: 'Which brokers are supported?',
      a: 'Currently Zerodha, Upstox, and Angel One. More brokers are being added based on demand — let us know which one you use.',
    },
    {
      q: 'What LLM does StockCraft use?',
      a: 'Claude Sonnet by default on the managed plan. On the self-hosted plan you bring your own OpenAI, Anthropic, or Gemini API key — that makes usage free on our end.',
    },
    {
      q: 'Can I export research to Excel?',
      a: 'Yes — every research result and AI conversation can be exported as CSV or PDF directly from the dashboard.',
    },
  ];

  agents = [
    {
      icon: 'bar_chart',
      title: 'Fundamental Agent',
      desc: 'Reads earnings reports, balance sheets, and ratios. Flags companies with strong financials before the market notices.',
    },
    {
      icon: 'show_chart',
      title: 'Technical Agent',
      desc: 'Watches RSI, MACD, momentum, and chart patterns across NSE/BSE in real time.',
    },
    {
      icon: 'article',
      title: 'News Agent',
      desc: 'Parses headlines, regulatory filings, and earnings call transcripts. Surfaces what matters, ignores the noise.',
    },
    {
      icon: 'security',
      title: 'Risk Agent',
      desc: 'Tracks volatility, beta, and drawdown across your portfolio. Alerts you before exposure becomes dangerous.',
    },
  ];

  steps = [
    {
      n: '01',
      title: 'Connect',
      desc: 'Link your Zerodha account in 30 seconds via secure read-only API. No passwords stored.',
      icon: 'lock',
    },
    {
      n: '02',
      title: 'Discover',
      desc: 'Let AI agents scan the market based on your risk profile and surface opportunities across NSE/BSE.',
      icon: 'manage_search',
    },
    {
      n: '03',
      title: 'Ask',
      desc: 'Chat with your AI analyst about any stock, sector rotation, or what\'s happening in your portfolio.',
      icon: 'chat_bubble_outline',
    },
    {
      n: '04',
      title: 'Decide',
      desc: 'You make the trade. Optionally automate weekly scans. Full control stays with you, always.',
      icon: 'check_circle_outline',
    },
  ];

  constructor(
    private router: Router,
    private demoService: DemoService,
    private ngZone: NgZone,
  ) {}

  ngAfterViewInit(): void {
    const video = this.splashVideo.nativeElement;
    video.muted = true;
    video.play().catch(() => {});

    this.splashTimeout = setTimeout(() => this.onSplashEnd(), 6000);

    this.ngZone.runOutsideAngular(() => {
      window.addEventListener('scroll', this.onScroll, { passive: true });
    });
  }

  ngOnDestroy(): void {
    if (this.splashTimeout) clearTimeout(this.splashTimeout);
    window.removeEventListener('scroll', this.onScroll);
  }

  private onScroll = (): void => {
    const scrolled = window.scrollY > 60;
    if (scrolled !== this.isScrolled) {
      this.ngZone.run(() => { this.isScrolled = scrolled; });
    }
  };

  onSplashEnd(): void {
    if (this.splashFading) return;
    if (this.splashTimeout) { clearTimeout(this.splashTimeout); this.splashTimeout = null; }
    this.splashFading = true;
    setTimeout(() => { this.showSplash = false; }, 600);
  }

  toggleFaq(i: number): void {
    this.openFaq = this.openFaq === i ? null : i;
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
