import { Injectable } from '@angular/core';
import { Router, UrlTree } from '@angular/router';
import { Observable, of } from 'rxjs';
import { map, catchError } from 'rxjs/operators';
import { AuthService } from '../services/auth.service';
import { DemoService } from '../services/demo.service';

@Injectable({ providedIn: 'root' })
export class BrokerGuard {
  constructor(
    private authService: AuthService,
    private demoService: DemoService,
    private router: Router
  ) {}

  canActivate(): Observable<boolean | UrlTree> | boolean | UrlTree {
    if (this.demoService.isDemo) return true;
    if (!this.authService.isAuthenticated()) return this.router.createUrlTree(['/login']);

    // Already verified valid this session — skip the API call
    if (this.authService.isBrokerVerified) return true;

    // One API call per page-load session to check broker token validity
    return this.authService.getBrokerStatus().pipe(
      map((res: any) => {
        if (res.linked && res.valid) {
          this.authService.markBrokerVerified(true);
          return true;
        }
        this.authService.markBrokerVerified(false);
        return this.router.createUrlTree(['/connect-kite']);
      }),
      catchError(() => {
        this.authService.markBrokerVerified(false);
        return of(this.router.createUrlTree(['/connect-kite']));
      })
    );
  }
}
