import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../services/auth.service';
import { DemoService } from '../../services/demo.service';
import { TierService } from '../../services/tier.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent {
  mode: 'login' | 'signup' | 'forgot' = 'login';

  email: string = '';
  password: string = '';
  name: string = '';
  confirmPassword: string = '';

  isLoading: boolean = false;
  error: string = '';
  successMessage: string = '';

  constructor(
    private authService: AuthService,
    private demoService: DemoService,
    private tierService: TierService,
    private router: Router
  ) {
    if (this.authService.isAuthenticated()) {
      this.router.navigate(['/dashboard']);
    }
  }

  switchMode(mode: 'login' | 'signup' | 'forgot'): void {
    this.mode = mode;
    this.error = '';
    this.successMessage = '';
  }

  onSubmit(): void {
    if (this.mode === 'login') {
      this.login();
    } else if (this.mode === 'signup') {
      this.signup();
    } else {
      this.sendForgotPassword();
    }
  }

  login(): void {
    if (!this.email.trim() || !this.password) {
      this.error = 'Email and password are required';
      return;
    }
    this.isLoading = true;
    this.error = '';
    this.authService.login(this.email, this.password).subscribe({
      next: (res) => {
        if (res.success) {
          this.demoService.exitDemo();
          this.navigateAfterAuth();
        } else {
          this.error = res.error || 'Login failed';
        }
        this.isLoading = false;
      },
      error: (err) => {
        this.error = err.error?.error || 'Login failed. Please check your credentials.';
        this.isLoading = false;
      }
    });
  }

  signup(): void {
    if (!this.name.trim()) { this.error = 'Name is required'; return; }
    if (!this.email.trim()) { this.error = 'Email is required'; return; }
    if (this.password.length < 8) { this.error = 'Password must be at least 8 characters'; return; }
    if (this.password !== this.confirmPassword) { this.error = 'Passwords do not match'; return; }

    this.isLoading = true;
    this.error = '';
    this.authService.register(this.email, this.password, this.name).subscribe({
      next: (res) => {
        if (res.success) {
          this.demoService.exitDemo();
          this.navigateAfterAuth();
        } else {
          this.error = res.error || 'Registration failed';
        }
        this.isLoading = false;
      },
      error: (err) => {
        this.error = err.error?.error || 'Registration failed. Please try again.';
        this.isLoading = false;
      }
    });
  }

  private navigateAfterAuth(): void {
    this.tierService.getOnboardingStatus().subscribe({
      next: (res) => {
        if (res.onboarding_completed === false) {
          this.router.navigate(['/onboarding']);
        } else {
          this.router.navigate(['/dashboard']);
        }
      },
      error: () => {
        // On network error, proceed to dashboard (non-blocking)
        this.router.navigate(['/dashboard']);
      }
    });
  }

  sendForgotPassword(): void {
    if (!this.email.trim()) {
      this.error = 'Please enter your email address';
      return;
    }
    this.isLoading = true;
    this.error = '';
    this.authService.forgotPassword(this.email).subscribe({
      next: () => {
        this.successMessage = 'If that email is registered, you\'ll receive a reset link shortly.';
        this.isLoading = false;
      },
      error: () => {
        // Always show success to prevent email enumeration
        this.successMessage = 'If that email is registered, you\'ll receive a reset link shortly.';
        this.isLoading = false;
      }
    });
  }
}
