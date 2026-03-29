import { Routes } from '@angular/router';
import { HomeComponent } from './components/home/home.component';
import { LoginComponent } from './components/login/login.component';
import { DashboardComponent } from './components/dashboard/dashboard.component';
import { AccountComponent } from './components/account/account.component';
import { AuthGuard } from './guards/auth.guard';
import { BrokerGuard } from './guards/broker.guard';

export const routes: Routes = [
  { path: '', component: HomeComponent, pathMatch: 'full' },
  { path: 'login', component: LoginComponent },
  {
    path: 'reset-password',
    loadComponent: () => import('./components/reset-password/reset-password.component').then(m => m.ResetPasswordComponent)
  },
  {
    path: 'connect-kite',
    loadComponent: () => import('./components/connect-kite/connect-kite.component').then(m => m.ConnectKiteComponent),
    canActivate: [AuthGuard]
  },
  { path: 'dashboard', component: DashboardComponent, canActivate: [AuthGuard, BrokerGuard] },
  {
    path: 'discover',
    loadComponent: () => import('./components/discover/discover.component').then(m => m.DiscoverComponent),
    canActivate: [AuthGuard, BrokerGuard]
  },
  {
    path: 'positions',
    loadComponent: () => import('./components/positions/positions.component').then(m => m.PositionsComponent),
    canActivate: [AuthGuard, BrokerGuard]
  },
  // Automation content lives under /account (Automation tab)
  { path: 'automation', redirectTo: '/account', pathMatch: 'full' },
  { path: 'account', component: AccountComponent, canActivate: [AuthGuard, BrokerGuard] },
  // Legacy redirect — /trading-agent now points to /dashboard
  { path: 'trading-agent', redirectTo: '/dashboard', pathMatch: 'full' },
  { path: '**', redirectTo: '/' }
];
