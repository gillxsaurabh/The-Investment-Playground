import { Component, OnInit, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ChatService, ChatMessage } from '../../services/chat.service';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat.component.html',
  styleUrls: ['./chat.component.scss']
})
export class ChatComponent implements OnInit, AfterViewChecked {
  @ViewChild('messagesContainer') private messagesContainer!: ElementRef;

  messages: ChatMessage[] = [];
  newMessage: string = '';
  isLoading: boolean = false;
  isChatOpen: boolean = false;
  showSpeechBubble: boolean = false;

  constructor(private chatService: ChatService, private sanitizer: DomSanitizer) {}

  ngOnInit(): void {
    this.chatService.messages$.subscribe(messages => {
      this.messages = messages;
    });
    // Show speech bubble 1.2s after load, auto-dismiss after 5.5s
    setTimeout(() => { this.showSpeechBubble = true; }, 1200);
    setTimeout(() => { this.showSpeechBubble = false; }, 6700);
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
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
          // Add error message
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
      next: () => {
        console.log('Chat cleared');
      },
      error: (err) => {
        console.error('Failed to clear chat:', err);
      }
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
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  formatUserMessage(text: string): SafeHtml {
    // Escape HTML to prevent XSS, then wrap @mentions in colored spans
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    const highlighted = escaped.replace(/@([A-Za-z]+)/g, '<span class="mention">@$1</span>');
    return this.sanitizer.bypassSecurityTrustHtml(highlighted);
  }

  formatAIMessage(text: string): SafeHtml {
    // Escape HTML first to prevent XSS
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

    // Bold **text**
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic *text* (avoid matching remaining lone asterisks)
    html = html.replace(/\*([^*\n]+?)\*/g, '<em>$1</em>');
    // Headers ### or ## or #
    html = html.replace(/^#{1,3}\s+(.+)$/gm, '<strong class="chat-heading">$1</strong>');
    // Monospace `code`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bullet lines starting with - or •
    html = html.replace(/^[-•]\s+(.+)$/gm, '<span class="chat-bullet">$1</span>');
    // Score bar lines (lines containing █ or ░)
    html = html.replace(/^(.+?)\s+(█[█░]+\s+[\d.]+\/5)$/gm, '<span class="score-row"><span class="score-label">$1</span><span class="score-bar">$2</span></span>');
    // ASCII table separator lines (─────)
    html = html.replace(/^[─\-]{3,}.*$/gm, '<span class="chat-divider"></span>');
    // Double newline → paragraph break
    html = html.replace(/\n\n/g, '</p><p class="chat-p">');
    // Single newline → line break
    html = html.replace(/\n/g, '<br>');

    return this.sanitizer.bypassSecurityTrustHtml(`<p class="chat-p">${html}</p>`);
  }
}
