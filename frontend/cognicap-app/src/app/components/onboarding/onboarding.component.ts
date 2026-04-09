import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { TierService } from '../../services/tier.service';

@Component({
  selector: 'app-onboarding',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './onboarding.component.html',
  styleUrls: ['./onboarding.component.scss']
})
export class OnboardingComponent implements OnInit {
  selectedTier: number | null = null;
  completing = false;

  tiers = [
    {
      id: 1,
      name: 'Stock Explorer',
      tagline: 'Explore the market',
      price: '₹199/mo',
      features: [
        'Live market data (Nifty 100)',
        'Market indices (Nifty & Sensex)',
        'AI-powered stock discovery',
        'Portfolio simulator',
        'Platform LLM API included',
      ],
      missing: ['Live portfolio sync', 'Personal holdings analysis'],
      accent: '#d4a843',
      badge: 'Standard',
    },
    {
      id: 2,
      name: 'The Executer',
      tagline: 'Full experience',
      price: '₹499/mo',
      features: [
        'Everything in Stock Explorer',
        'Live portfolio sync via Kite',
        'Personal holdings analysis',
        'Sell audit pipeline',
        'Weekly automation',
        'Platform LLM API included',
      ],
      missing: ['Bring Your Own LLM API'],
      accent: '#5b8def',
      badge: 'Popular',
    },
    {
      id: 3,
      name: 'Lone Wolf',
      tagline: 'Full control, zero cost',
      price: 'Free',
      features: [
        'Everything in The Executer',
        'Bring Your Own LLM API',
        'Runs on your API quotas',
        'No platform charges',
      ],
      missing: [],
      accent: '#00c176',
      badge: 'Free',
    },
  ];

  constructor(private tierService: TierService, private router: Router) {}

  ngOnInit(): void {
    // If onboarding already completed, go to dashboard
    this.tierService.getOnboardingStatus().subscribe(res => {
      if (res.onboarding_completed) {
        this.router.navigate(['/dashboard']);
      }
    });
  }

  selectTier(tierId: number): void {
    this.selectedTier = tierId;
  }

  proceed(): void {
    if (!this.selectedTier) return;
    this.completing = true;

    this.tierService.completeOnboarding().subscribe({
      next: () => {
        this.completing = false;
        if (this.selectedTier === 3) {
          // Rockstar: configure APIs first
          this.router.navigate(['/account']);
        } else if (this.selectedTier === 2) {
          // Ideal: link Kite first, then paywall
          this.router.navigate(['/connect-kite']);
        } else {
          // General: just go to paywall
          this.router.navigate(['/subscribe']);
        }
      },
      error: () => {
        this.completing = false;
        // On error, navigate to dashboard anyway
        this.router.navigate(['/dashboard']);
      }
    });
  }
}
