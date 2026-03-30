import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnChanges,
  SimpleChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { AuditHolding, AuditSummary } from '../../services/kite.service';

export interface AuditStep {
  step: number;
  agent: string;
  role: string;
  status: 'pending' | 'running' | 'completed';
  duration_ms?: number;
}

@Component({
  selector: 'app-stock-audit-chart',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './stock-audit-chart.component.html',
  styleUrls: ['./stock-audit-chart.component.scss'],
})
export class StockAuditChartComponent implements OnChanges {
  @Input() holdings: AuditHolding[] = [];
  @Input() summary: AuditSummary | null = null;
  @Input() isRunning = false;
  @Input() steps: AuditStep[] = [];
  @Input() lastRunAt: string | null = null;
  @Input() pipelineMessage = '';

  @Output() onRunAudit   = new EventEmitter<void>();
  @Output() onSelectStock = new EventEmitter<AuditHolding>();

  readonly componentKeys = [
    'technical', 'fundamental', 'relative_strength', 'news', 'position',
  ] as const;

  readonly componentLabels: Record<string, string> = {
    technical:         'Technical',
    fundamental:       'Fundamental',
    relative_strength: 'Rel. Str.',
    news:              'News',
    position:          'Position',
  };

  get sortedHoldings(): AuditHolding[] {
    return [...this.holdings].sort((a, b) => b.health_score - a.health_score);
  }

  ngOnChanges(_: SimpleChanges): void {}

  getCompVal(h: AuditHolding, key: string): number {
    return (h.health_components as unknown as Record<string, number>)?.[key] ?? 0;
  }

  // Each component is scored out of 2 (5 × 2 = 10 total)
  getCompPct(h: AuditHolding, key: string): number {
    return Math.min(100, (this.getCompVal(h, key) / 2) * 100);
  }

  getCompColor(h: AuditHolding, key: string): string {
    const pct = this.getCompVal(h, key) / 2;
    if (pct >= 0.75) return '#22c55e';
    if (pct >= 0.50) return '#eab308';
    if (pct >= 0.25) return '#f97316';
    return '#ef4444';
  }

  getLabelColor(label: string): string {
    const map: Record<string, string> = {
      HEALTHY:  '#22c55e',
      STABLE:   '#eab308',
      WATCH:    '#f97316',
      CRITICAL: '#ef4444',
    };
    return map[label] ?? '#a1a1aa';
  }

  getVerdictClass(verdict: string): string {
    const map: Record<string, string> = {
      HOLD:          'verdict-hold',
      MONITOR:       'verdict-monitor',
      CONSIDER_EXIT: 'verdict-consider',
      EXIT:          'verdict-exit',
    };
    return map[verdict] ?? '';
  }

  getLabelClass(label: string): string {
    const map: Record<string, string> = {
      HEALTHY:  'label-healthy',
      STABLE:   'label-stable',
      WATCH:    'label-watch',
      CRITICAL: 'label-critical',
    };
    return map[label] ?? '';
  }

  formatVerdict(v: string): string {
    return v.replace(/_/g, ' ');
  }

  formatDate(dt: string): string {
    if (!dt) return '';
    return new Date(dt).toLocaleDateString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }

  trackBySymbol(_: number, h: AuditHolding): string {
    return h.symbol;
  }
}
