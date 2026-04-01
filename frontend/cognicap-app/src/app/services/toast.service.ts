import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: number;
  type: ToastType;
  message: string;
  duration: number;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private counter = 0;
  private toastsSubject = new BehaviorSubject<Toast[]>([]);
  toasts$ = this.toastsSubject.asObservable();

  success(message: string, duration = 4000): void {
    this.add('success', message, duration);
  }

  error(message: string, duration = 6000): void {
    this.add('error', message, duration);
  }

  warning(message: string, duration = 5000): void {
    this.add('warning', message, duration);
  }

  info(message: string, duration = 4000): void {
    this.add('info', message, duration);
  }

  dismiss(id: number): void {
    this.toastsSubject.next(
      this.toastsSubject.value.filter(t => t.id !== id)
    );
  }

  private add(type: ToastType, message: string, duration: number): void {
    const id = ++this.counter;
    const toast: Toast = { id, type, message, duration };
    this.toastsSubject.next([...this.toastsSubject.value, toast]);
    if (duration > 0) {
      setTimeout(() => this.dismiss(id), duration);
    }
  }
}
