import { Component, OnInit, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
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

  constructor(private chatService: ChatService) {}

  ngOnInit(): void {
    this.chatService.messages$.subscribe(messages => {
      this.messages = messages;
    });
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
}
