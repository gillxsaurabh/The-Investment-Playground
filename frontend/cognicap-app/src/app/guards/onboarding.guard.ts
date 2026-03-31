import { Injectable } from '@angular/core';
import { Router, UrlTree } from '@angular/router';
import { Observable } from 'rxjs';
import { map, catchError, timeout } from 'rxjs/operators';
import { of } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { TierService } from '../services/tier.service';
import { DemoService } from '../services/demo.service';

@Injectable({ providedIn: 'root' })
export class OnboardingGuard {
  constructor(
    private authService: AuthService,
    private tierService: TierService,
    private demoService: DemoService,
    private router: Router
  ) {}

  canActivate(): Observable<boolean | UrlTree> | boolean | UrlTree {
    // Demo mode bypasses onboarding
    if (this.demoService.isDemo) return true;
    if (!this.authService.isAuthenticated()) return this.router.createUrlTree(['/login']);

    return this.tierService.getOnboardingStatus().pipe(
      timeout(5000), // Never hang longer than 5 seconds
      map((res: any) => {
        if (res.success && res.onboarding_completed) {
          return true;
        }
        return this.router.createUrlTree(['/onboarding']);
      }),
      catchError(() => of(true)) // On error or timeout, allow through
    );
  }
}
