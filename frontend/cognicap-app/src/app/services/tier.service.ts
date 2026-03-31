import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

export interface TierInfo {
  tier: number;
  tier_name: string;
  plan: string;
  has_broker: boolean;
  has_llm_keys: boolean;
  llm_providers: string[];
  needs_payment: boolean;
}

@Injectable({ providedIn: 'root' })
export class TierService {
  private apiUrl = '/api/auth';

  private tierSubject = new BehaviorSubject<TierInfo | null>(null);
  public tier$ = this.tierSubject.asObservable();

  constructor(private http: HttpClient) {}

  fetchTier(): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/tier`).pipe(
      tap(res => {
        if (res.success) {
          this.tierSubject.next({
            tier: res.tier,
            tier_name: res.tier_name,
            plan: res.plan || 'general',
            has_broker: res.has_broker,
            has_llm_keys: res.has_llm_keys,
            llm_providers: res.llm_providers || [],
            needs_payment: res.needs_payment,
          });
        }
      })
    );
  }

  get currentTier(): TierInfo | null {
    return this.tierSubject.value;
  }

  getLLMKeys(): Observable<{ success: boolean; providers: string[] }> {
    return this.http.get<any>(`${this.apiUrl}/llm-keys`);
  }

  saveLLMKey(provider: string, apiKey: string): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/llm-keys`, { provider, api_key: apiKey }).pipe(
      tap(res => { if (res.success) this.fetchTier().subscribe(); })
    );
  }

  deleteLLMKey(provider: string): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/llm-keys/${provider}`).pipe(
      tap(res => { if (res.success) this.fetchTier().subscribe(); })
    );
  }

  getPlan(): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/plan`).pipe(
      tap(res => { if (res.success) this.tierSubject.next(res as TierInfo); })
    );
  }

  setPlan(plan: string): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/plan`, { plan }).pipe(
      tap(res => { if (res.success) this.tierSubject.next(res as TierInfo); })
    );
  }

  getOnboardingStatus(): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/onboarding-status`);
  }

  completeOnboarding(): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/onboarding-complete`, {});
  }

  getSubscriptionStatus(): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/subscription`);
  }

  activateSubscription(): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/subscription/activate`, {});
  }
}
