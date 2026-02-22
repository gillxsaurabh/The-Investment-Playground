import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject } from 'rxjs';
import { tap } from 'rxjs/operators';

export interface ChatMessage {
  id: string;
  text: string;
  isUser: boolean;
  timestamp: Date;
}

export interface ChatResponse {
  success: boolean;
  response?: string;
  session_id?: string;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private apiUrl = 'http://localhost:5000/api';
  private messagesSubject = new BehaviorSubject<ChatMessage[]>([]);
  public messages$ = this.messagesSubject.asObservable();
  private sessionId: string;

  constructor(private http: HttpClient) {
    this.sessionId = this.generateSessionId();
    // Add welcome message
    this.addMessage({
      id: this.generateMessageId(),
      text: 'Hello! I\'m your CogniCap AI assistant. How can I help you with your portfolio today?',
      isUser: false,
      timestamp: new Date()
    });
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private generateMessageId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private addMessage(message: ChatMessage): void {
    const currentMessages = this.messagesSubject.value;
    this.messagesSubject.next([...currentMessages, message]);
  }

  sendMessage(message: string): Observable<ChatResponse> {
    // Add user message immediately
    this.addMessage({
      id: this.generateMessageId(),
      text: message,
      isUser: true,
      timestamp: new Date()
    });

    return this.http.post<ChatResponse>(`${this.apiUrl}/chat/send`, {
      message,
      session_id: this.sessionId,
      access_token: localStorage.getItem('access_token') || ''
    }).pipe(
      tap(response => {
        if (response.success && response.response) {
          // Add AI response
          this.addMessage({
            id: this.generateMessageId(),
            text: response.response,
            isUser: false,
            timestamp: new Date()
          });
        }
      })
    );
  }

  clearChat(): Observable<any> {
    return this.http.post(`${this.apiUrl}/chat/clear`, {
      session_id: this.sessionId
    }).pipe(
      tap(() => {
        // Clear messages and add welcome message
        this.messagesSubject.next([]);
        this.sessionId = this.generateSessionId();
        this.addMessage({
          id: this.generateMessageId(),
          text: 'Hello! I\'m your CogniCap AI assistant. How can I help you with your portfolio today?',
          isUser: false,
          timestamp: new Date()
        });
      })
    );
  }

  getMessages(): ChatMessage[] {
    return this.messagesSubject.value;
  }
}
