import { Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { KiteService } from '../services/kite.service';

@Injectable({
  providedIn: 'root'
})
export class AuthGuard {
  constructor(
    private kiteService: KiteService,
    private router: Router
  ) {}

  canActivate(): boolean {
    if (this.kiteService.isAuthenticated()) {
      return true;
    }
    
    this.router.navigate(['/login']);
    return false;
  }
}
