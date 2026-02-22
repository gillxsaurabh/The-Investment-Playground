import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnChanges,
  OnDestroy,
  SimpleChanges,
  ViewChild,
  ElementRef,
  AfterViewInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SimulatorPosition } from '../../services/simulator.service';
import {
  Chart,
  ScatterController,
  LineController,
  LineElement,
  BarController,
  BarElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';

Chart.register(
  ScatterController, LineController, LineElement, BarController, BarElement,
  PointElement, LinearScale, CategoryScale, Tooltip, Legend,
  Filler, annotationPlugin
);

interface PortfolioVitals {
  totalInvested: number;
  currentValue: number;
  totalPnl: number;
  roiPct: number;
}

@Component({
  selector: 'app-positions-chart',
  standalone: true,
  imports: [CommonModule],
  template: `
    <!-- Portfolio Vitals Row -->
    <div class="vitals-row" *ngIf="positions.length > 0">
      <div class="vital-tile">
        <span class="vital-label">Total Invested</span>
        <span class="vital-value">{{ formatCurrency(vitals.totalInvested) }}</span>
      </div>
      <div class="vital-tile">
        <span class="vital-label">Current Value</span>
        <span class="vital-value">{{ formatCurrency(vitals.currentValue) }}</span>
      </div>
      <div class="vital-tile">
        <span class="vital-label">Total P/L</span>
        <span class="vital-value" [class.up]="vitals.totalPnl >= 0" [class.down]="vitals.totalPnl < 0">
          {{ formatPnl(vitals.totalPnl) }}
        </span>
      </div>
      <div class="vital-tile">
        <span class="vital-label">ROI</span>
        <span class="vital-value" [class.up]="vitals.roiPct >= 0" [class.down]="vitals.roiPct < 0">
          {{ vitals.roiPct >= 0 ? '+' : '' }}{{ vitals.roiPct.toFixed(2) }}%
        </span>
      </div>
    </div>

    <!-- Charts Row -->
    <div class="charts-split">
      <div class="chart-half scatter-half">
        <canvas #chartCanvas></canvas>
      </div>
      <div class="chart-half bar-half">
        <canvas #barCanvas></canvas>
      </div>
    </div>
  `,
  styles: [`
    :host { display: block; padding: 12px 14px 8px; }

    .vitals-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin-bottom: 10px;
    }

    .vital-tile {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 8px;
      padding: 10px 12px;
      text-align: center;
    }

    .vital-label {
      display: block;
      font-size: 9px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #6b7280;
      margin-bottom: 4px;
    }

    .vital-value {
      display: block;
      font-size: 16px;
      font-weight: 700;
      color: #f0f0f0;
      font-variant-numeric: tabular-nums;

      &.up { color: #22c55e; }
      &.down { color: #ef4444; }
    }

    .charts-split {
      display: flex;
      gap: 8px;
      min-height: 0;
    }

    .chart-half {
      flex: 1;
      min-width: 0;
    }

    .scatter-half { flex: 3; }
    .bar-half  { flex: 2; }

    canvas {
      width: 100% !important;
      height: 220px !important;
    }

  `],
})
export class PositionsChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() positions: SimulatorPosition[] = [];
  @Input() exitingIds: { [tradeId: string]: boolean } = {};
  @Output() onExit = new EventEmitter<string>();

  @ViewChild('chartCanvas') canvasRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('barCanvas') barCanvasRef!: ElementRef<HTMLCanvasElement>;

  vitals: PortfolioVitals = { totalInvested: 0, currentValue: 0, totalPnl: 0, roiPct: 0 };

  private chart: Chart | null = null;
  private barChart: Chart | null = null;

  ngAfterViewInit(): void {
    this.createChart();
    this.createBarChart();
    if (this.positions.length > 0) {
      this.computeVitals();
      this.updateChart();
      this.updateBarChart();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['positions']) {
      this.computeVitals();
      if (this.chart) {
        this.updateChart();
        this.updateBarChart();
      }
    }
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
    this.barChart?.destroy();
  }

  formatPnl(value: number): string {
    const formatted = new Intl.NumberFormat('en-IN', {
      style: 'currency', currency: 'INR', maximumFractionDigits: 0,
    }).format(Math.abs(value));
    return (value >= 0 ? '+' : '-') + formatted;
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency', currency: 'INR', maximumFractionDigits: 0,
    }).format(value);
  }

  private getPct(pos: SimulatorPosition): number {
    if (!pos.ltp || !pos.entry_price) return 0;
    return ((pos.ltp - pos.entry_price) / pos.entry_price) * 100;
  }

  private computeVitals(): void {
    let invested = 0;
    let current = 0;
    for (const pos of this.positions) {
      invested += pos.entry_price * pos.quantity;
      current += (pos.ltp || pos.entry_price) * pos.quantity;
    }
    const pnl = current - invested;
    this.vitals = {
      totalInvested: invested,
      currentValue: current,
      totalPnl: pnl,
      roiPct: invested > 0 ? (pnl / invested) * 100 : 0,
    };
  }

  // ── Risk Radar Scatter Chart ────────────────────────────────────────

  private createChart(): void {
    const ctx = this.canvasRef.nativeElement.getContext('2d');
    if (!ctx) return;

    this.chart = new Chart(ctx, {
      type: 'scatter',
      data: { datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: {
            title: {
              display: true,
              text: 'Distance to SL (%)',
              color: 'rgba(200,200,200,0.8)',
              font: { size: 10 },
            },
            grid: { color: 'rgba(255,255,255,0.12)' },
            ticks: {
              color: 'rgba(200,200,200,0.8)',
              font: { size: 10 },
              callback: (val: any) => `${Number(val).toFixed(1)}%`,
            },
          },
          y: {
            title: {
              display: true,
              text: 'Unrealized P/L (%)',
              color: 'rgba(200,200,200,0.8)',
              font: { size: 10 },
            },
            grid: { color: 'rgba(255,255,255,0.12)' },
            ticks: {
              color: 'rgba(200,200,200,0.8)',
              font: { size: 10 },
              callback: (val: any) => `${Number(val).toFixed(1)}%`,
            },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1a1a1a',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1,
            titleColor: '#f0f0f0',
            bodyColor: '#9ca3af',
            titleFont: { size: 11, weight: 'bold' },
            bodyFont: { size: 11 },
            padding: 10,
            cornerRadius: 8,
            callbacks: {
              label: (tooltipCtx: any) => {
                const raw = tooltipCtx.raw;
                const pos = raw?.pos as SimulatorPosition | undefined;
                if (!pos) return '';
                const pnlStr = this.formatPnl(pos.unrealized_pnl || 0);
                return [
                  `${pos.symbol}`,
                  `LTP: ${pos.ltp?.toFixed(2)}`,
                  `P/L: ${pnlStr}`,
                ];
              },
            },
          },
          annotation: { annotations: {} },
        },
      },
    });
  }

  private updateChart(): void {
    if (!this.chart) return;

    const dataPoints = this.positions.map(pos => {
      const ltp = pos.ltp || pos.entry_price;
      const sl = pos.current_sl ?? pos.stop_loss ?? 0;
      const distToSl = ltp > 0 ? ((ltp - sl) / ltp) * 100 : 0;
      const unrealizedPct = pos.entry_price > 0
        ? ((ltp - pos.entry_price) / pos.entry_price) * 100
        : 0;
      return { x: distToSl, y: unrealizedPct, pos };
    });

    const greenPoints = dataPoints.filter(p => p.y >= 0);
    const redPoints = dataPoints.filter(p => p.y < 0);

    const datasets: any[] = [];

    if (greenPoints.length > 0) {
      datasets.push({
        label: 'Profit',
        data: greenPoints,
        backgroundColor: 'rgba(34, 197, 94, 0.8)',
        borderColor: '#22c55e',
        borderWidth: 1.5,
        pointRadius: 7,
        pointHoverRadius: 10,
        pointStyle: 'circle',
      });
    }

    if (redPoints.length > 0) {
      datasets.push({
        label: 'Loss',
        data: redPoints,
        backgroundColor: 'rgba(239, 68, 68, 0.8)',
        borderColor: '#ef4444',
        borderWidth: 1.5,
        pointRadius: 7,
        pointHoverRadius: 10,
        pointStyle: 'circle',
      });
    }

    this.chart.data.datasets = datasets;

    // Annotations: reference lines + danger zone
    const annotations: any = {
      breakeven: {
        type: 'line',
        yMin: 0, yMax: 0,
        borderColor: 'rgba(255,255,255,0.2)',
        borderWidth: 1.5,
        borderDash: [6, 4],
        label: {
          display: true,
          content: 'BREAKEVEN',
          position: 'end',
          backgroundColor: 'transparent',
          color: 'rgba(255,255,255,0.25)',
          font: { size: 8, weight: 'bold' },
        },
      },
      slWall: {
        type: 'line',
        xMin: 0, xMax: 0,
        borderColor: '#ef4444',
        borderWidth: 2,
        label: {
          display: true,
          content: 'SL HIT',
          position: 'start',
          backgroundColor: 'rgba(239,68,68,0.12)',
          color: '#ef4444',
          font: { size: 8, weight: 'bold' },
          padding: { top: 2, bottom: 2, left: 4, right: 4 },
        },
      },
      dangerLine: {
        type: 'line',
        xMin: 1, xMax: 1,
        borderColor: 'rgba(239,68,68,0.5)',
        borderWidth: 1,
        borderDash: [4, 3],
      },
      dangerZone: {
        type: 'box',
        xMin: 0, xMax: 1,
        backgroundColor: 'rgba(239,68,68,0.06)',
        borderWidth: 0,
      },
    };

    // Per-point stock name labels (positioned directly next to dot)
    for (const pt of dataPoints) {
      const sym = pt.pos.symbol;
      annotations[`label_${sym}`] = {
        type: 'label',
        xValue: pt.x,
        yValue: pt.y,
        content: sym,
        color: 'rgba(240,240,240,0.7)',
        font: { size: 9, weight: 'bold' },
        xAdjust: 12,
        yAdjust: -12,
      };
    }

    // Dynamic axis bounds with padding so labels never clip
    if (dataPoints.length > 0) {
      const xVals = dataPoints.map(p => p.x);
      const yVals = dataPoints.map(p => p.y);
      const xMin = Math.min(0, ...xVals);
      const xMax = Math.max(...xVals);
      const yMin = Math.min(...yVals);
      const yMax = Math.max(0, ...yVals);
      const xPad = Math.max((xMax - xMin) * 0.15, 0.5);
      const yPad = Math.max((yMax - yMin) * 0.2, 0.5);

      (this.chart.options.scales as any).x.min = Math.floor((xMin - xPad) * 2) / 2;
      (this.chart.options.scales as any).x.max = Math.ceil((xMax + xPad) * 2) / 2;
      (this.chart.options.scales as any).y.min = Math.floor((yMin - yPad) * 2) / 2;
      (this.chart.options.scales as any).y.max = Math.ceil((yMax + yPad) * 2) / 2;
    }

    (this.chart.options.plugins as any).annotation.annotations = annotations;
    this.chart.update('none');
  }

  // ── Bar Chart (current % snapshot) ───────────────────────────────────

  private createBarChart(): void {
    const ctx = this.barCanvasRef?.nativeElement.getContext('2d');
    if (!ctx) return;

    this.barChart = new Chart(ctx, {
      type: 'bar',
      data: { labels: [], datasets: [] },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: {
            grid: { color: 'rgba(255,255,255,0.12)' },
            ticks: {
              color: 'rgba(200,200,200,0.8)',
              font: { size: 10 },
              callback: (val) => `${val}%`,
            },
          },
          y: {
            grid: { display: false },
            ticks: {
              color: '#f0f0f0',
              font: { size: 10, weight: 'bold' },
            },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1a1a1a',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1,
            titleColor: '#f0f0f0',
            bodyColor: '#9ca3af',
            titleFont: { size: 11, weight: 'bold' },
            bodyFont: { size: 11 },
            padding: 10,
            cornerRadius: 8,
            callbacks: {
              label: (tooltipCtx: any) => {
                const pct = tooltipCtx.parsed.x;
                const symbol = tooltipCtx.label;
                const pos = this.positions.find(p => p.symbol === symbol);
                const pnl = pos?.unrealized_pnl || 0;
                const pnlStr = new Intl.NumberFormat('en-IN', {
                  style: 'currency', currency: 'INR', maximumFractionDigits: 0,
                }).format(pnl);
                return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}% (${pnlStr})`;
              },
            },
          },
          annotation: {
            annotations: {
              zeroLine: {
                type: 'line',
                xMin: 0, xMax: 0,
                borderColor: 'rgba(255,255,255,0.3)',
                borderWidth: 1.5,
                borderDash: [6, 4],
              },
            },
          },
        },
      },
    });
  }

  private updateBarChart(): void {
    if (!this.barChart) return;

    const sorted = [...this.positions]
      .map(pos => ({
        symbol: pos.symbol,
        pct: this.getPct(pos),
      }))
      .sort((a, b) => b.pct - a.pct);

    const labels = sorted.map(s => s.symbol);
    const values = sorted.map(s => Math.round(s.pct * 100) / 100);
    const colors = values.map(v => v >= 0 ? '#22c55e' : '#ef4444');
    const bgColors = values.map(v => v >= 0 ? 'rgba(34, 197, 94, 0.7)' : 'rgba(239, 68, 68, 0.7)');

    this.barChart.data.labels = labels;
    this.barChart.data.datasets = [{
      data: values,
      backgroundColor: bgColors,
      borderColor: colors,
      borderWidth: 1,
      borderRadius: 3,
      barPercentage: 0.7,
      categoryPercentage: 0.8,
    }];

    this.barChart.update('none');
  }
}
