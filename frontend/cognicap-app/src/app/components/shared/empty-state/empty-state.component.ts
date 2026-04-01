import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './empty-state.component.html',
  styleUrls: ['./empty-state.component.scss']
})
export class EmptyStateComponent {
  @Input() icon: string = 'inbox';
  @Input() title: string = 'Nothing here yet';
  @Input() description: string = '';
  @Input() ctaLabel: string = '';
  @Output() ctaClick = new EventEmitter<void>();
}
