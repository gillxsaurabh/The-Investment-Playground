import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-connect-kite',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './connect-kite.component.html',
  styleUrls: ['./connect-kite.component.scss']
})
export class ConnectKiteComponent {
  loginUrl: string | null = null;
  requestToken = '';
  status: 'idle' | 'fetching-url' | 'awaiting-token' | 'linking' | 'error' = 'idle';
  errorMsg = '';

  constructor(private authService: AuthService, private router: Router) {
    // Already verified — send straight to dashboard
    if (this.authService.isBrokerVerified) {
      this.router.navigate(['/dashboard']);
    }
  }

  openKiteLogin(): void {
    this.status = 'fetching-url';
    this.errorMsg = '';
    this.authService.getBrokerLoginUrl().subscribe({
      next: res => {
        if (res.success && res.login_url) {
          this.loginUrl = res.login_url;
          this.status = 'awaiting-token';
          window.open(res.login_url, '_blank');
        } else {
          this.status = 'error';
          this.errorMsg = 'Could not get Kite login URL. Check your API key configuration.';
        }
      },
      error: () => {
        this.status = 'error';
        this.errorMsg = 'Could not get Kite login URL. Check your API key configuration.';
      }
    });
  }

  linkAccount(): void {
    if (!this.requestToken.trim()) {
      this.errorMsg = 'Please enter the request token';
      return;
    }
    this.status = 'linking';
    this.errorMsg = '';
    this.authService.linkBroker(this.requestToken.trim()).subscribe({
      next: (res: any) => {
        if (res.success) {
          this.router.navigate(['/dashboard']);
        } else {
          this.status = 'error';
          this.errorMsg = res.error || 'Failed to link account. Try again.';
        }
      },
      error: (err: any) => {
        this.status = 'error';
        this.errorMsg = err.error?.error || 'Failed to link account. The token may have expired.';
      }
    });
  }

  logout(): void {
    this.authService.logout();
  }
}
