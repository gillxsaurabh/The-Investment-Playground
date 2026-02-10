import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject } from 'rxjs';
import { map, tap } from 'rxjs/operators';

export interface AuthResponse {
  success: boolean;
  access_token?: string;
  user?: {
    name: string;
    email: string;
    user_id: string;
  };
  error?: string;
}

export interface Holdings {
  success: boolean;
  holdings?: any[];
  error?: string;
}

export interface PortfolioSummary {
  success: boolean;
  summary?: {
    total_holdings: number;
    total_investment: number;
    current_value: number;
    total_pnl: number;
    pnl_percentage: number;
    positions_count: number;
  };
  error?: string;
}

export interface TopPerformer {
  tradingsymbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
  pnl_percentage: number;
}

export interface TopPerformers {
  success: boolean;
  top_gainers?: TopPerformer[];
  top_losers?: TopPerformer[];
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class KiteService {
  private apiUrl = 'http://localhost:5000/api';
  private accessTokenSubject = new BehaviorSubject<string | null>(this.getStoredToken());
  public accessToken$ = this.accessTokenSubject.asObservable();
  private userSubject = new BehaviorSubject<any>(this.getStoredUser());
  public user$ = this.userSubject.asObservable();

  constructor(private http: HttpClient) {}

  private getStoredToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private getStoredUser(): any {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  }

  getLoginUrl(): Observable<any> {
    return this.http.get(`${this.apiUrl}/auth/login-url`);
  }

  authenticate(requestToken: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.apiUrl}/auth/authenticate`, {
      request_token: requestToken
    }).pipe(
      tap(response => {
        if (response.success && response.access_token) {
          localStorage.setItem('access_token', response.access_token);
          localStorage.setItem('user', JSON.stringify(response.user));
          this.accessTokenSubject.next(response.access_token);
          this.userSubject.next(response.user);
        }
      })
    );
  }

  verifyToken(): Observable<boolean> {
    const token = this.getStoredToken();
    if (!token) {
      return new Observable(observer => {
        observer.next(false);
        observer.complete();
      });
    }

    return this.http.post<AuthResponse>(`${this.apiUrl}/auth/verify`, {
      access_token: token
    }).pipe(
      map(response => {
        if (response.success && response.user) {
          this.userSubject.next(response.user);
          return true;
        }
        return false;
      })
    );
  }

  getHoldings(): Observable<Holdings> {
    const token = this.getStoredToken();
    return this.http.post<Holdings>(`${this.apiUrl}/portfolio/holdings`, {
      access_token: token
    });
  }

  getPortfolioSummary(): Observable<PortfolioSummary> {
    const token = this.getStoredToken();
    return this.http.post<PortfolioSummary>(`${this.apiUrl}/portfolio/summary`, {
      access_token: token
    });
  }

  getTopPerformers(): Observable<TopPerformers> {
    const token = this.getStoredToken();
    return this.http.post<TopPerformers>(`${this.apiUrl}/portfolio/top-performers`, {
      access_token: token
    });
  }

  logout(): void {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    this.accessTokenSubject.next(null);
    this.userSubject.next(null);
  }

  isAuthenticated(): boolean {
    return !!this.getStoredToken();
  }
}
