import { Component, Input, Output, EventEmitter, OnInit, HostBinding } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../../services/auth.service';

interface NavItem {
  label: string;
  icon: string;
  route: string;
}

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive],
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.scss']
})
export class SidebarComponent implements OnInit {
  @Input() userName: string = '';
  @Input() brokerLinked: boolean = false;
  @Input() mobileOpen: boolean = false;
  @Output() onLogout = new EventEmitter<void>();
  @Output() closeRequest = new EventEmitter<void>();

  @HostBinding('class.mobile-open') get isOpen() { return this.mobileOpen; }

  isCollapsed = false;

  constructor(public auth: AuthService) {}

  navMain: NavItem[] = [
    { label: 'Dashboard',  icon: 'dashboard',         route: '/dashboard' },
    { label: 'Discover',   icon: 'search',             route: '/discover' },
    { label: 'Positions',  icon: 'candlestick_chart',  route: '/positions' },
  ];

  navSettings: NavItem[] = [
    { label: 'Account',   icon: 'manage_accounts',  route: '/account' },
  ];

  ngOnInit(): void {
    const saved = localStorage.getItem('stockcraft-sidebar-collapsed');
    this.isCollapsed = saved === 'true';
    this.applyWidth();
  }

  toggle(): void {
    this.isCollapsed = !this.isCollapsed;
    localStorage.setItem('stockcraft-sidebar-collapsed', String(this.isCollapsed));
    this.applyWidth();
  }

  private applyWidth(): void {
    document.documentElement.style.setProperty(
      '--sidebar-w',
      this.isCollapsed ? '56px' : '240px'
    );
  }

  logout(): void {
    this.onLogout.emit();
  }

  closeOnNav(): void {
    this.closeRequest.emit();
  }
}
