import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of, throwError } from 'rxjs';
import { map, tap, catchError, switchMap } from 'rxjs/operators';
import { Router } from '@angular/router';

export interface User {
  id: number;
  email: string;
  name: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
}

export interface LoginResponse {
  success: boolean;
  access_token?: string;
  refresh_token?: string;
  user?: User;
  broker_linked?: boolean;
  error?: string;
}

export interface RegisterResponse {
  success: boolean;
  access_token?: string;
  refresh_token?: string;
  user?: User;
  error?: string;
}

export interface MeResponse {
  success: boolean;
  user?: User;
  broker_linked?: boolean;
  broker?: {
    broker_user_id: string;
    broker_user_name: string;
    linked_at: string;
  } | null;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = '/api/auth';

  private userSubject = new BehaviorSubject<User | null>(this.loadUser());
  public user$ = this.userSubject.asObservable();

  private brokerLinkedSubject = new BehaviorSubject<boolean>(this.loadBrokerLinked());
  public brokerLinked$ = this.brokerLinkedSubject.asObservable();

  // In-memory flag: was broker status verified valid this session?
  private brokerVerifiedSubject = new BehaviorSubject<boolean>(false);
  get isBrokerVerified(): boolean { return this.brokerVerifiedSubject.value; }

  markBrokerVerified(valid: boolean): void {
    this.brokerVerifiedSubject.next(valid);
    if (!valid) {
      localStorage.setItem('broker_linked', 'false');
      this.brokerLinkedSubject.next(false);
    } else {
      localStorage.setItem('broker_linked', 'true');
      this.brokerLinkedSubject.next(true);
    }
  }

  private isRefreshing = false;

  constructor(private http: HttpClient, private router: Router) {}

  // --- Token storage ---

  getAccessToken(): string | null {
    return localStorage.getItem('jwt_access_token');
  }

  getRefreshToken(): string | null {
    return localStorage.getItem('jwt_refresh_token');
  }

  private storeTokens(access: string, refresh: string): void {
    localStorage.setItem('jwt_access_token', access);
    localStorage.setItem('jwt_refresh_token', refresh);
  }

  private clearTokens(): void {
    localStorage.removeItem('jwt_access_token');
    localStorage.removeItem('jwt_refresh_token');
    localStorage.removeItem('user');
    localStorage.removeItem('broker_linked');
    // Also clean up legacy keys
    localStorage.removeItem('access_token');
  }

  private storeUser(user: User): void {
    localStorage.setItem('user', JSON.stringify(user));
    this.userSubject.next(user);
  }

  private loadUser(): User | null {
    const s = localStorage.getItem('user');
    try { return s ? JSON.parse(s) : null; } catch { return null; }
  }

  private loadBrokerLinked(): boolean {
    return localStorage.getItem('broker_linked') === 'true';
  }

  // --- Auth state ---

  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  get currentUser(): User | null {
    return this.userSubject.value;
  }

  get isBrokerLinked(): boolean {
    return this.brokerLinkedSubject.value;
  }

  // --- Register ---

  register(email: string, password: string, name: string): Observable<RegisterResponse> {
    return this.http.post<RegisterResponse>(`${this.apiUrl}/register`, {
      email, password, name
    }).pipe(
      tap(res => {
        if (res.success && res.access_token && res.refresh_token && res.user) {
          this.storeTokens(res.access_token, res.refresh_token);
          this.storeUser(res.user);
        }
      })
    );
  }

  // --- Login ---

  login(email: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.apiUrl}/login`, {
      email, password
    }).pipe(
      tap(res => {
        if (res.success && res.access_token && res.refresh_token && res.user) {
          this.storeTokens(res.access_token, res.refresh_token);
          this.storeUser(res.user);
          localStorage.setItem('broker_linked', String(res.broker_linked ?? false));
          this.brokerLinkedSubject.next(res.broker_linked ?? false);
        }
      })
    );
  }

  // --- Refresh ---

  refreshAccessToken(): Observable<string> {
    if (this.isRefreshing) {
      return throwError(() => new Error('Refresh already in progress'));
    }

    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      this.logout();
      return throwError(() => new Error('No refresh token'));
    }

    this.isRefreshing = true;

    return this.http.post<{ success: boolean; access_token?: string; refresh_token?: string }>(
      `${this.apiUrl}/refresh`,
      { refresh_token: refreshToken }
    ).pipe(
      tap(res => {
        this.isRefreshing = false;
        if (res.success && res.access_token && res.refresh_token) {
          this.storeTokens(res.access_token, res.refresh_token);
        } else {
          this.logout();
        }
      }),
      map(res => {
        if (res.success && res.access_token) return res.access_token;
        throw new Error('Refresh failed');
      }),
      catchError(err => {
        this.isRefreshing = false;
        this.logout();
        return throwError(() => err);
      })
    );
  }

  // --- Get profile ---

  fetchMe(): Observable<MeResponse> {
    return this.http.get<MeResponse>(`${this.apiUrl}/me`).pipe(
      tap(res => {
        if (res.success && res.user) {
          this.storeUser(res.user);
          localStorage.setItem('broker_linked', String(res.broker_linked ?? false));
          this.brokerLinkedSubject.next(res.broker_linked ?? false);
        }
      })
    );
  }

  // --- Logout ---

  logout(): void {
    // Try to revoke on server (fire and forget)
    const token = this.getAccessToken();
    if (token) {
      this.http.post(`${this.apiUrl}/logout`, {}).subscribe({ error: () => {} });
    }
    this.clearTokens();
    this.userSubject.next(null);
    this.brokerLinkedSubject.next(false);
    this.router.navigate(['/login']);
  }

  // --- Broker linking ---

  getBrokerLoginUrl(): Observable<{ success: boolean; login_url?: string }> {
    return this.http.get<{ success: boolean; login_url?: string }>(`${this.apiUrl}/broker/login-url`);
  }

  linkBroker(requestToken: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/broker/link`, { request_token: requestToken }).pipe(
      tap((res: any) => {
        if (res.success) {
          this.markBrokerVerified(true);
        }
      })
    );
  }

  getBrokerStatus(): Observable<any> {
    return this.http.get(`${this.apiUrl}/broker/status`);
  }

  // --- Password management ---

  changePassword(currentPassword: string, newPassword: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/change-password`, {
      current_password: currentPassword,
      new_password: newPassword
    });
  }

  forgotPassword(email: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/forgot-password`, { email });
  }

  resetPassword(token: string, newPassword: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/reset-password`, {
      token,
      new_password: newPassword
    });
  }
}
