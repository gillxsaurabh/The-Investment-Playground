import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { KiteService } from '../../services/kite.service';
import { DemoService } from '../../services/demo.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent {
  requestToken: string = '';
  loginUrl: string = '';
  isLoading: boolean = false;
  error: string = '';
  showLoginUrl: boolean = false;

  constructor(
    private kiteService: KiteService,
    private demoService: DemoService,
    private router: Router
  ) {}

  getLoginUrl(): void {
    this.isLoading = true;
    this.error = '';
    
    this.kiteService.getLoginUrl().subscribe({
      next: (response) => {
        if (response.success) {
          this.loginUrl = response.login_url;
          this.showLoginUrl = true;
          // Open in new window
          window.open(this.loginUrl, '_blank');
        }
        this.isLoading = false;
      },
      error: (err) => {
        this.error = 'Failed to get login URL. Please try again.';
        this.isLoading = false;
      }
    });
  }

  login(): void {
    if (!this.requestToken.trim()) {
      this.error = 'Please enter the request token';
      return;
    }

    this.isLoading = true;
    this.error = '';

    this.kiteService.authenticate(this.requestToken).subscribe({
      next: (response) => {
        if (response.success) {
          this.demoService.exitDemo();   // clear demo mode on real login
          this.router.navigate(['/dashboard']);
        } else {
          this.error = response.error || 'Authentication failed';
        }
        this.isLoading = false;
      },
      error: (err) => {
        this.error = err.error?.error || 'Authentication failed. Please check your request token.';
        this.isLoading = false;
      }
    });
  }
}
