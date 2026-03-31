import { Routes } from '@angular/router';
import { HomeComponent } from './components/home/home.component';
import { LoginComponent } from './components/login/login.component';
import { DashboardComponent } from './components/dashboard/dashboard.component';
import { AccountComponent } from './components/account/account.component';
import { AuthGuard } from './guards/auth.guard';
import { BrokerGuard } from './guards/broker.guard';
import { OnboardingGuard } from './guards/onboarding.guard';
import { AdminGuard } from './guards/admin.guard';

export const routes: Routes = [
  { path: '', component: HomeComponent, pathMatch: 'full' },
  { path: 'login', component: LoginComponent },
  {
    path: 'reset-password',
    loadComponent: () => import('./components/reset-password/reset-password.component').then(m => m.ResetPasswordComponent)
  },
  // Onboarding — shown once after first login
  {
    path: 'onboarding',
    loadComponent: () => import('./components/onboarding/onboarding.component').then(m => m.OnboardingComponent),
    canActivate: [AuthGuard]
  },
  // Paywall — dummy subscription page
  {
    path: 'subscribe',
    loadComponent: () => import('./components/paywall/paywall.component').then(m => m.PaywallComponent),
    canActivate: [AuthGuard]
  },
  // Admin panel — auth check only, admin check handled inside component
  {
    path: 'admin',
    loadComponent: () => import('./components/admin/admin.component').then(m => m.AdminComponent),
    canActivate: [AuthGuard]
  },
  // Connect Kite — accessible without BrokerGuard (user may not have broker yet)
  {
    path: 'connect-kite',
    loadComponent: () => import('./components/connect-kite/connect-kite.component').then(m => m.ConnectKiteComponent),
    canActivate: [AuthGuard]
  },
  // Market-data routes — no BrokerGuard (admin token fallback for market data)
  {
    path: 'dashboard',
    component: DashboardComponent,
    canActivate: [AuthGuard, OnboardingGuard]
  },
  {
    path: 'discover',
    loadComponent: () => import('./components/discover/discover.component').then(m => m.DiscoverComponent),
    canActivate: [AuthGuard, OnboardingGuard]
  },
  // Simulator positions — paper trading only, no broker needed
  {
    path: 'positions',
    loadComponent: () => import('./components/positions/positions.component').then(m => m.PositionsComponent),
    canActivate: [AuthGuard, OnboardingGuard]
  },
  // Account — no BrokerGuard so Tier 1 users can configure APIs
  { path: 'automation', redirectTo: '/account', pathMatch: 'full' },
  { path: 'account', component: AccountComponent, canActivate: [AuthGuard] },
  // Legacy redirect
  { path: 'trading-agent', redirectTo: '/dashboard', pathMatch: 'full' },
  { path: '**', redirectTo: '/' }
];
