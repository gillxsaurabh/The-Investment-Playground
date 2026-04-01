import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export type SkeletonVariant = 'text' | 'circle' | 'card' | 'table-row';

@Component({
  selector: 'app-skeleton',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="skeleton"
         [class]="'skeleton--' + variant"
         [style.width]="width"
         [style.height]="height"
         [attr.aria-hidden]="true">
      <ng-container *ngIf="variant === 'text'">
        <div class="skeleton-line" *ngFor="let i of linesArr"></div>
      </ng-container>
      <ng-container *ngIf="variant === 'table-row'">
        <div class="skeleton-cell" *ngFor="let w of cellWidths" [style.width]="w"></div>
      </ng-container>
    </div>
  `,
  styleUrls: ['./skeleton.component.scss']
})
export class SkeletonComponent {
  @Input() variant: SkeletonVariant = 'text';
  @Input() lines: number = 3;
  @Input() width?: string;
  @Input() height?: string;

  cellWidths = ['120px', '80px', '80px', '60px', '90px', '80px'];

  get linesArr(): number[] {
    return Array.from({ length: this.lines }, (_, i) => i);
  }
}
