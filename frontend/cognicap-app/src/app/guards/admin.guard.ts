import { Injectable } from '@angular/core';
import { Router, UrlTree } from '@angular/router';
import { Observable } from 'rxjs';
import { map, catchError, timeout } from 'rxjs/operators';
import { of } from 'rxjs';
import { AuthService } from '../services/auth.service';

@Injectable({ providedIn: 'root' })
export class AdminGuard {
  constructor(private authService: AuthService, private router: Router) {}

  canActivate(): Observable<boolean | UrlTree> | boolean | UrlTree {
    if (!this.authService.isAuthenticated()) {
      return this.router.createUrlTree(['/login']);
    }

    // Fetch fresh user data so is_admin reflects DB state (not stale localStorage)
    return this.authService.fetchMe().pipe(
      timeout(5000),
      map(res => {
        if (res.success && res.user?.is_admin) {
          return true;
        }
        return this.router.createUrlTree(['/dashboard']);
      }),
      catchError(() => {
        // Fall back to cached value on network error
        return of(this.authService.isAdmin ? true : this.router.createUrlTree(['/dashboard']));
      })
    );
  }
}
