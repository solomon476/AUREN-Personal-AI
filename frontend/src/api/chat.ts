/**
 * Chat and Streaming API service.
 * Supports persistent conversations, message history, and resilient Server-Sent Events (SSE) streaming.
 */

import { supabase } from '../lib/supabase';
import { apiClient } from './client';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: 'system' | 'user' | 'assistant';
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface ChatStreamCallbacks {
  onMetadata?: (meta: { conversation_id: string; user_message_id: string; title: string }) => void;
  onToken?: (token: string) => void;
  onDone?: (done: { message_id: string; finish_reason?: string; model?: string }) => void;
  onError?: (error: string) => void;
}

export async function listConversations(): Promise<Conversation[]> {
  return apiClient.get<Conversation[]>('/chat/conversations');
}

export async function createConversation(title?: string): Promise<Conversation> {
  return apiClient.post<Conversation>('/chat/conversations', { title: title || 'New Conversation' });
}

export async function getConversationMessages(conversationId: string): Promise<ChatMessage[]> {
  return apiClient.get<ChatMessage[]>(`/chat/conversations/${conversationId}/messages`);
}

export async function streamChat(
  message: string,
  conversationId?: string,
  callbacks?: ChatStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${API_BASE_URL.replace(/\/$/, '')}/chat/completions`;
  const idempotencyKey = `req-${crypto.randomUUID()}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  };

  // Inject active Supabase user session token
  if (supabase) {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }
    } catch {
      // Session unavailable
    }
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      message,
      conversation_id: conversationId || null,
      idempotency_key: idempotencyKey,
    }),
    signal,
  });

  if (!response.ok) {
    let errorDetail = `Streaming request failed with status ${response.status}`;
    try {
      const errorJson = await response.json();
      if (errorJson && typeof errorJson.detail === 'string') {
        errorDetail = errorJson.detail;
      }
    } catch {
      // Not JSON
    }
    callbacks?.onError?.(errorDetail);
    throw new Error(errorDetail);
  }

  if (!response.body) {
    callbacks?.onError?.('Response body is null');
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const block of lines) {
        const lineParts = block.split('\n');
        let currentEvent = 'message';
        let currentData = '';

        for (const line of lineParts) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6).trim();
          }
        }

        if (!currentData) continue;

        try {
          const parsed = JSON.parse(currentData);

          if (currentEvent === 'metadata') {
            callbacks?.onMetadata?.(parsed);
          } else if (currentEvent === 'token') {
            callbacks?.onToken?.(parsed.text || '');
          } else if (currentEvent === 'done') {
            callbacks?.onDone?.(parsed);
          } else if (currentEvent === 'error') {
            callbacks?.onError?.(parsed.detail || 'Stream error occurred');
          }
        } catch {
          // Plain text fallback
          if (currentEvent === 'token') {
            callbacks?.onToken?.(currentData);
          }
        }
      }
    }
  } catch (err) {
    if (signal?.aborted) {
      loggerInfo('Chat stream intentionally aborted by user.');
    } else {
      const msg = err instanceof Error ? err.message : 'Unknown stream error';
      callbacks?.onError?.(msg);
      throw err;
    }
  }
}

function loggerInfo(msg: string) {
  // Silent or debug log in dev
  if (import.meta.env.DEV) {
    console.debug(`[AUREN Chat] ${msg}`);
  }
}

