import { Component } from '@angular/core';
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
export class HomeComponent {
  // Secret logo-tap counter — 5 clicks within 3s opens dev login
  private logoClicks = 0;
  private logoTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private router: Router, private demoService: DemoService) {}

  enterDemo(): void {
    this.demoService.enterDemo();
    this.router.navigate(['/dashboard']);
  }

  goToKiteLogin(): void {
    // Placeholder — Kite OAuth flow will be wired here
  }

  onLogoClick(): void {
    this.logoClicks++;
    if (this.logoTimer) clearTimeout(this.logoTimer);

    if (this.logoClicks >= 5) {
      this.logoClicks = 0;
      this.router.navigate(['/login']);
      return;
    }

    this.logoTimer = setTimeout(() => { this.logoClicks = 0; }, 3000);
  }

  openDevLogin(): void {
    this.router.navigate(['/login']);
  }
}
