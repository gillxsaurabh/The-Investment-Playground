import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { TierService } from '../../services/tier.service';

@Component({
  selector: 'app-paywall',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './paywall.component.html',
  styleUrls: ['./paywall.component.scss']
})
export class PaywallComponent {
  subscribing = false;
  subscribed = false;
  error = '';

  constructor(private tierService: TierService, private router: Router) {}

  subscribe(): void {
    this.subscribing = true;
    this.error = '';
    this.tierService.activateSubscription().subscribe({
      next: (res) => {
        this.subscribing = false;
        if (res.success) {
          this.subscribed = true;
          setTimeout(() => this.router.navigate(['/dashboard']), 1500);
        }
      },
      error: () => {
        this.subscribing = false;
        this.error = 'Subscription failed. Please try again.';
      }
    });
  }

  skip(): void {
    this.router.navigate(['/dashboard']);
  }
}
