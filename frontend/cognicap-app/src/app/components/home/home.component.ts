import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { DemoService } from '../../services/demo.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss'],
})
export class HomeComponent {
  constructor(private router: Router, private demoService: DemoService) {}

  enterDemo(): void {
    this.demoService.enterDemo();
    this.router.navigate(['/dashboard']);
  }

  goToKiteLogin(): void {
    // Placeholder — Kite OAuth flow will be wired here
  }
}
