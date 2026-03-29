import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnChanges,
  SimpleChanges,
  AfterViewInit,
  OnDestroy,
  ElementRef,
  ViewChild,
  NgZone,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { AuditHolding, AuditSummary } from '../../services/kite.service';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

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
export class StockAuditChartComponent implements OnChanges, AfterViewInit, OnDestroy {
  @Input() holdings: AuditHolding[] = [];
  @Input() summary: AuditSummary | null = null;
  @Input() isRunning = false;
  @Input() steps: AuditStep[] = [];
  @Input() lastRunAt: string | null = null;
  @Input() pipelineMessage = '';

  @Output() onRunAudit  = new EventEmitter<void>();
  @Output() onSelectStock = new EventEmitter<AuditHolding>();

  @ViewChild('chartCanvas') chartCanvas!: ElementRef<HTMLCanvasElement>;

  private chart: Chart | null = null;
  private viewInitialized = false;

  constructor(private ngZone: NgZone) {}

  ngAfterViewInit(): void {
    this.viewInitialized = true;
    if (this.holdings.length > 0) {
      this.renderChart();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['holdings'] && this.viewInitialized) {
      this.ngZone.runOutsideAngular(() => {
        setTimeout(() => this.renderChart(), 50);
      });
    }
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }

  private renderChart(): void {
    if (!this.chartCanvas || this.holdings.length === 0) return;

    this.chart?.destroy();

    const sorted = [...this.holdings].sort((a, b) => a.health_score - b.health_score);
    const labels = sorted.map(h => h.symbol);

    const componentColors = {
      technical:         'rgba(108, 99, 255, 0.85)',
      fundamental:       'rgba(34, 197, 94, 0.85)',
      relative_strength: 'rgba(249, 115, 22, 0.85)',
      news:              'rgba(234, 179, 8, 0.85)',
      position:          'rgba(99, 195, 255, 0.85)',
    };

    const componentLabels: Record<string, string> = {
      technical:         'Technical',
      fundamental:       'Fundamental',
      relative_strength: 'Rel. Strength',
      news:              'News',
      position:          'Position',
    };

    const datasets = (['technical', 'fundamental', 'relative_strength', 'news', 'position'] as const).map(key => ({
      label: componentLabels[key],
      data: sorted.map(h => h.health_components?.[key] ?? 0),
      backgroundColor: componentColors[key],
      borderWidth: 0,
    }));

    this.chart = new Chart(this.chartCanvas.nativeElement, {
      type: 'bar',
      data: { labels, datasets },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#a1a1aa',
              boxWidth: 12,
              font: { size: 11 },
              padding: 16,
            },
          },
          tooltip: {
            callbacks: {
              afterBody: (items: any[]) => {
                const idx  = items[0]?.dataIndex;
                const h    = sorted[idx];
                if (!h) return [];
                return [
                  `Total: ${h.health_score}/10`,
                  `Verdict: ${h.audit_verdict}`,
                  h.ai_reasoning ? `AI: ${h.ai_reasoning.substring(0, 80)}…` : '',
                ].filter(Boolean);
              },
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            min: 0,
            max: 10,
            grid: { color: 'rgba(255,255,255,0.05)' },
            ticks: { color: '#52525b', stepSize: 2 },
          },
          y: {
            stacked: true,
            grid: { display: false },
            ticks: {
              color: (ctx: any) => {
                const h = sorted[ctx.index];
                if (!h) return '#a1a1aa';
                return this.getLabelColor(h.health_label);
              },
              font: { size: 12, weight: 'bold' },
            },
          },
        },
        onClick: (_: any, elements: any[]) => {
          if (!elements.length) return;
          const h = sorted[elements[0].index];
          if (h) {
            this.ngZone.run(() => this.onSelectStock.emit(h));
          }
        },
      },
    });
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

  formatDate(dt: string): string {
    if (!dt) return '';
    return new Date(dt).toLocaleDateString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }

  get chartHeight(): number {
    return Math.max(180, this.holdings.length * 36 + 60);
  }

  trackBySymbol(_: number, h: AuditHolding): string {
    return h.symbol;
  }
}
