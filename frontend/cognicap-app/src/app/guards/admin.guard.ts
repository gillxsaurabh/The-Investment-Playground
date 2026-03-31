import { Injectable } from '@angular/core';
import { Router, UrlTree } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Injectable({ providedIn: 'root' })
export class AdminGuard {
  constructor(private authService: AuthService, private router: Router) {}

  canActivate(): boolean | UrlTree {
    if (!this.authService.isAuthenticated()) {
      return this.router.createUrlTree(['/login']);
    }
    if (this.authService.isAdmin) {
      return true;
    }
    return this.router.createUrlTree(['/dashboard']);
  }
}
