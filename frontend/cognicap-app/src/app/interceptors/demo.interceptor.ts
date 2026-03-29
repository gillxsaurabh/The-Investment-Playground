import { HttpRequest, HttpHandlerFn, HttpEvent, HttpResponse } from '@angular/common/http';
import { Observable, of, throwError } from 'rxjs';
import { inject } from '@angular/core';
import { DemoService, DEMO_DATA } from '../services/demo.service';

// Endpoints that return demo data (read-only) -- matched by suffix
const MOCK_MAP: Record<string, () => unknown> = {
  '/api/portfolio/holdings':      () => DEMO_DATA.holdings,
  '/api/portfolio/summary':       () => DEMO_DATA.portfolio_summary,
  '/api/portfolio/top-performers':() => DEMO_DATA.top_performers,
  '/api/market/indices':          () => DEMO_DATA.market_indices,
  '/api/market/top-stocks':       () => DEMO_DATA.top_stocks,
  '/api/market/stocks':           () => DEMO_DATA.top_stocks,
  '/api/simulator/positions':     () => DEMO_DATA.simulator_state,
  '/api/trading/mode':            () => DEMO_DATA.trading_mode,
  '/api/automation/status':       () => DEMO_DATA.automation_status,
  '/api/automation/history':      () => DEMO_DATA.automation_history,
  '/api/audit/results':           () => DEMO_DATA.audit_results,
};

// Endpoints that are blocked in demo -- show Kite prompt instead
const BLOCKED_PATTERNS = [
  '/api/simulator/execute',
  '/api/simulator/close',
  '/api/simulator/reset',
  '/api/automation/run-now',
  '/api/automation/enable',
  '/api/chat/send',
  '/api/chat/clear',
  '/api/sector-research',
  '/api/trade/calculate-exits',
  '/api/trading/execute',
  '/api/trading/close',
];

export function demoInterceptor(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn
): Observable<HttpEvent<unknown>> {
  const demoService = inject(DemoService);
  if (!demoService.isDemo) return next(req);

  const url = req.url;

  // Check blocked endpoints first
  if (BLOCKED_PATTERNS.some(p => url.includes(p))) {
    demoService.showKitePrompt();
    return throwError(() => ({ status: 403, error: { demo_blocked: true } }));
  }

  // Check mock data endpoints
  for (const [path, dataFn] of Object.entries(MOCK_MAP)) {
    if (url.includes(path)) {
      return of(new HttpResponse({ status: 200, body: dataFn() }));
    }
  }

  // Auth endpoints -- swallow in demo
  if (url.includes('/api/auth/')) {
    return of(new HttpResponse({ status: 200, body: { success: true, ...DEMO_DATA.user } }));
  }

  // Analysis and audit run endpoints -- block and prompt
  if (url.includes('/api/analyze') || url.includes('/api/audit/run')) {
    demoService.showKitePrompt();
    return throwError(() => ({ status: 403, error: { demo_blocked: true } }));
  }

  return next(req);
}
