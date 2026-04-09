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

  @Output() onRunAudit    = new EventEmitter<void>();
  @Output() onSelectStock = new EventEmitter<AuditHolding>();

  viewMode: 'bucket' | 'card' | 'table' = 'bucket';
  activeFilter: string | null = null;
  expandedCard: string | null = null;

  // Bucket view
  readonly bucketLabels: string[] = ['HEALTHY', 'STABLE', 'WATCH', 'CRITICAL'];
  expandedBuckets = new Set<string>();

  // ── Radar geometry ──────────────────────────────────────────────────────────
  // SVG viewBox "0 0 140 130", center shifted to leave room for corner labels
  private readonly R       = 38;   // pentagon radius
  private readonly CX      = 70;   // center x
  private readonly CY      = 65;   // center y (shifted down slightly for top label)
  private readonly LABEL_R = 51;   // label distance from center

  readonly axisIndices = [0, 1, 2, 3, 4];

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

  readonly shortLabels: Record<string, string> = {
    technical:         'TECH',
    fundamental:       'FUND',
    relative_strength: 'RS',
    news:              'NEWS',
    position:          'POS',
  };

  // ── Computed collections ───────────────────────────────────────────────────

  get sortedHoldings(): AuditHolding[] {
    const base = [...this.holdings].sort((a, b) => b.health_score - a.health_score);
    return this.activeFilter ? base.filter(h => h.health_label === this.activeFilter) : base;
  }

  ngOnChanges(_: SimpleChanges): void {}

  // ── Filter / view controls ─────────────────────────────────────────────────

  setFilter(label: string): void {
    this.activeFilter = this.activeFilter === label ? null : label;
  }

  toggleCard(symbol: string, event: Event): void {
    event.stopPropagation();
    this.expandedCard = this.expandedCard === symbol ? null : symbol;
  }

  // ── Bucket view helpers ────────────────────────────────────────────────────

  getBucket(label: string): AuditHolding[] {
    return [...this.holdings]
      .filter(h => h.health_label === label)
      .sort((a, b) => b.health_score - a.health_score);
  }

  getVisibleBucket(label: string): AuditHolding[] {
    const bucket = this.getBucket(label);
    return this.expandedBuckets.has(label) ? bucket : bucket.slice(0, 3);
  }

  toggleBucket(label: string, event: Event): void {
    event.stopPropagation();
    if (this.expandedBuckets.has(label)) {
      this.expandedBuckets.delete(label);
    } else {
      this.expandedBuckets.add(label);
    }
    // Trigger Angular change detection on Set mutation
    this.expandedBuckets = new Set(this.expandedBuckets);
  }

  getBucketGridCols(): string {
    return this.bucketLabels.map(label =>
      this.getBucket(label).length === 0 ? '44px' : '1fr'
    ).join(' ');
  }

  // ── Radar SVG helpers ──────────────────────────────────────────────────────

  /** Polygon points for the data fill (SVG `points` attribute string). */
  getRadarPoints(h: AuditHolding): string {
    return this.componentKeys.map((key, i) => {
      const angle    = (i * 2 * Math.PI / 5) - Math.PI / 2;
      const val      = this.getCompVal(h, key as string);
      const fraction = Math.max(0, Math.min(1, val / 2)); // 0–1
      const r        = Math.max(3, fraction * this.R);    // min 3px so zero scores still have a dot
      return `${this.CX + r * Math.cos(angle)},${this.CY + r * Math.sin(angle)}`;
    }).join(' ');
  }

  /** Polygon points for a concentric grid ring at `fraction` (0–1) of max radius. */
  getGridPoints(fraction: number): string {
    return this.axisIndices.map(i => {
      const angle = (i * 2 * Math.PI / 5) - Math.PI / 2;
      const r     = fraction * this.R;
      return `${this.CX + r * Math.cos(angle)},${this.CY + r * Math.sin(angle)}`;
    }).join(' ');
  }

  /** Line from center to each axis tip. */
  getAxisLine(index: number): { x1: number; y1: number; x2: number; y2: number } {
    const angle = (index * 2 * Math.PI / 5) - Math.PI / 2;
    return {
      x1: this.CX,
      y1: this.CY,
      x2: this.CX + this.R * Math.cos(angle),
      y2: this.CY + this.R * Math.sin(angle),
    };
  }

  /** Position for the corner label beyond each axis tip. */
  getLabelPos(index: number): { x: number; y: number } {
    const angle = (index * 2 * Math.PI / 5) - Math.PI / 2;
    return {
      x: this.CX + this.LABEL_R * Math.cos(angle),
      y: this.CY + this.LABEL_R * Math.sin(angle),
    };
  }

  /** SVG text-anchor for each corner label so it doesn't overflow. */
  getLabelAnchor(index: number): string {
    const cos = Math.cos((index * 2 * Math.PI / 5) - Math.PI / 2);
    if (cos > 0.25)  return 'start';
    if (cos < -0.25) return 'end';
    return 'middle';
  }

  /** SVG dominant-baseline for each corner label. */
  getLabelBaseline(index: number): string {
    const sin = Math.sin((index * 2 * Math.PI / 5) - Math.PI / 2);
    if (sin > 0.3)  return 'hanging';
    if (sin < -0.3) return 'auto';
    return 'middle';
  }

  /** Position for data-point dot at each axis. */
  getRadarDotPos(h: AuditHolding, index: number): { x: number; y: number } {
    const key      = this.componentKeys[index];
    const angle    = (index * 2 * Math.PI / 5) - Math.PI / 2;
    const val      = this.getCompVal(h, key as string);
    const fraction = Math.max(0, Math.min(1, val / 2));
    const r        = Math.max(3, fraction * this.R);
    return {
      x: this.CX + r * Math.cos(angle),
      y: this.CY + r * Math.sin(angle),
    };
  }

  // ── Existing helpers (unchanged) ───────────────────────────────────────────

  getCompVal(h: AuditHolding, key: string): number {
    return (h.health_components as unknown as Record<string, number>)?.[key] ?? 0;
  }

  getCompPct(h: AuditHolding, key: string): number {
    return Math.min(100, (this.getCompVal(h, key) / 2) * 100);
  }

  getCompColor(h: AuditHolding, key: string): string {
    const pct = this.getCompVal(h, key) / 2;
    if (pct >= 0.75) return '#00c176';
    if (pct >= 0.50) return '#d4b83a';
    if (pct >= 0.25) return '#e5973a';
    return '#d64545';
  }

  getLabelColor(label: string): string {
    const map: Record<string, string> = {
      HEALTHY:  '#00c176',
      STABLE:   '#d4b83a',
      WATCH:    '#e5973a',
      CRITICAL: '#d64545',
    };
    return map[label] ?? '#6a6a6a';
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
    return v?.replace(/_/g, ' ') ?? '';
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
