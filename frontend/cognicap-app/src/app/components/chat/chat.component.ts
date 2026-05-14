import { Component, OnInit, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ChatService, ChatMessage } from '../../services/chat.service';

interface Agent {
  name: string;
  icon: string;
  desc: string;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat.component.html',
  styleUrls: ['./chat.component.scss']
})
export class ChatComponent implements OnInit, AfterViewChecked {
  @ViewChild('messagesContainer') private messagesContainer!: ElementRef;
  @ViewChild('chatInput') chatInputRef!: ElementRef<HTMLInputElement>;

  messages: ChatMessage[] = [];
  newMessage: string = '';
  isLoading: boolean = false;
  isChatOpen: boolean = false;
  showSpeechBubble: boolean = false;

  // @mention autocomplete
  readonly agents: Agent[] = [
    { name: 'QuantAnalyst',        icon: 'bar_chart',      desc: 'Technical indicators — RSI, ADX, EMA' },
    { name: 'FundamentalsAnalyst', icon: 'analytics',      desc: 'Financials, ROE, revenue trends' },
    { name: 'NewsSentinel',        icon: 'newspaper',      desc: 'Breaking news & sentiment' },
    { name: 'StockAnalysis',       icon: 'manage_search',  desc: 'Full deep-dive on any stock' },
    { name: 'Portfolio',           icon: 'pie_chart',      desc: 'Your holdings & P&L overview' },
  ];

  showMentionMenu = false;
  filteredAgents: Agent[] = [];
  highlightedIndex = 0;

  constructor(private chatService: ChatService, private sanitizer: DomSanitizer) {}

  ngOnInit(): void {
    this.chatService.messages$.subscribe(messages => {
      this.messages = messages;
    });
    setTimeout(() => { this.showSpeechBubble = true; }, 1200);
    setTimeout(() => { this.showSpeechBubble = false; }, 6700);
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  onInputChange(value: string): void {
    const match = value.match(/@([A-Za-z]*)$/);
    if (match) {
      const query = match[1].toLowerCase();
      this.filteredAgents = this.agents.filter(a =>
        a.name.toLowerCase().startsWith(query)
      );
      this.showMentionMenu = this.filteredAgents.length > 0;
      this.highlightedIndex = 0;
    } else {
      this.showMentionMenu = false;
    }
  }

  selectMention(agent: Agent): void {
    const atIndex = this.newMessage.lastIndexOf('@');
    this.newMessage = this.newMessage.slice(0, atIndex) + '@' + agent.name + ' ';
    this.showMentionMenu = false;
    setTimeout(() => this.chatInputRef?.nativeElement?.focus(), 0);
  }

  closeMentionMenu(): void {
    setTimeout(() => { this.showMentionMenu = false; }, 150);
  }

  onInputKeydown(event: KeyboardEvent): void {
    if (this.showMentionMenu) {
      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          this.highlightedIndex = (this.highlightedIndex + 1) % this.filteredAgents.length;
          break;
        case 'ArrowUp':
          event.preventDefault();
          this.highlightedIndex = (this.highlightedIndex - 1 + this.filteredAgents.length) % this.filteredAgents.length;
          break;
        case 'Enter':
        case 'Tab':
          event.preventDefault();
          if (this.filteredAgents.length > 0) {
            this.selectMention(this.filteredAgents[this.highlightedIndex]);
          }
          break;
        case 'Escape':
          event.preventDefault();
          this.showMentionMenu = false;
          break;
      }
    } else if (event.key === 'Enter') {
      this.sendMessage();
    }
  }

  sendMessage(): void {
    if (!this.newMessage.trim() || this.isLoading) {
      return;
    }

    const message = this.newMessage.trim();
    this.newMessage = '';
    this.isLoading = true;

    this.chatService.sendMessage(message).subscribe({
      next: (response) => {
        this.isLoading = false;
        if (!response.success && response.error) {
          this.messages.push({
            id: `error_${Date.now()}`,
            text: `Error: ${response.error}`,
            isUser: false,
            timestamp: new Date()
          });
        }
      },
      error: (err) => {
        this.isLoading = false;
        this.messages.push({
          id: `error_${Date.now()}`,
          text: 'Failed to send message. Please try again.',
          isUser: false,
          timestamp: new Date()
        });
        console.error('Chat error:', err);
      }
    });
  }

  clearChat(): void {
    this.chatService.clearChat().subscribe({
      next: () => { console.log('Chat cleared'); },
      error: (err) => { console.error('Failed to clear chat:', err); }
    });
  }

  toggleChat(): void {
    this.isChatOpen = !this.isChatOpen;
  }

  private scrollToBottom(): void {
    try {
      if (this.messagesContainer) {
        this.messagesContainer.nativeElement.scrollTop =
          this.messagesContainer.nativeElement.scrollHeight;
      }
    } catch(err) {
      console.error('Scroll error:', err);
    }
  }

  formatTime(timestamp: Date): string {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  }

  formatUserMessage(text: string): SafeHtml {
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    const highlighted = escaped.replace(/@([A-Za-z]+)/g, '<span class="mention">@$1</span>');
    return this.sanitizer.bypassSecurityTrustHtml(highlighted);
  }

  formatAIMessage(text: string): SafeHtml {
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*\n]+?)\*/g, '<em>$1</em>');
    html = html.replace(/^#{1,3}\s+(.+)$/gm, '<strong class="chat-heading">$1</strong>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/^[-•]\s+(.+)$/gm, '<span class="chat-bullet">$1</span>');
    html = html.replace(/^(.+?)\s+(█[█░]+\s+[\d.]+\/5)$/gm, '<span class="score-row"><span class="score-label">$1</span><span class="score-bar">$2</span></span>');
    html = html.replace(/^[─\-]{3,}.*$/gm, '<span class="chat-divider"></span>');
    html = html.replace(/\n\n/g, '</p><p class="chat-p">');
    html = html.replace(/\n/g, '<br>');

    return this.sanitizer.bypassSecurityTrustHtml(`<p class="chat-p">${html}</p>`);
  }
}
