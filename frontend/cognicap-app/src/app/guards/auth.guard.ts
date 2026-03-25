import { Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { KiteService } from '../services/kite.service';
import { DemoService } from '../services/demo.service';

@Injectable({
  providedIn: 'root'
})
export class AuthGuard {
  constructor(
    private kiteService: KiteService,
    private demoService: DemoService,
    private router: Router
  ) {}

  canActivate(): boolean {
    if (this.demoService.isDemo || this.kiteService.isAuthenticated()) {
      return true;
    }

    this.router.navigate(['/']);
    return false;
  }
}
