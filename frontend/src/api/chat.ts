/**
 * Chat and Streaming API service.
 * Supports persistent conversations, message history, and resilient Server-Sent Events (SSE) streaming.
 */

import { supabase } from '../lib/supabase';
import { API_BASE_URL, apiClient } from './client';

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface AttachmentItem {
  type: 'image' | 'audio' | 'document' | 'file';
  url: string;
  name?: string;
  size?: number;
  duration?: number;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: 'system' | 'user' | 'assistant';
  content: string;
  created_at: string;
  idempotency_key?: string;
  metadata?: {
    attachments?: AttachmentItem[];
    interrupted?: boolean;
    [key: string]: unknown;
  };
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

export async function renameConversation(conversationId: string, title: string): Promise<Conversation> {
  return apiClient.patch<Conversation>(`/chat/conversations/${conversationId}`, { title });
}

export async function deleteConversation(conversationId: string): Promise<void> {
  return apiClient.delete<void>(`/chat/conversations/${conversationId}`);
}

export async function getConversationMessages(conversationId: string): Promise<ChatMessage[]> {
  return apiClient.get<ChatMessage[]>(`/chat/conversations/${conversationId}/messages`);
}

export async function streamChat(
  message: string,
  conversationId?: string,
  callbacks?: ChatStreamCallbacks,
  signal?: AbortSignal,
  idempotencyKey?: string,
  attachments?: AttachmentItem[],
): Promise<void> {
  const url = `${API_BASE_URL.replace(/\/$/, '')}/chat/completions`;
  const resolvedIdempotencyKey = idempotencyKey || `req-${crypto.randomUUID()}`;

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

  // Enforce an 18s initial connection and token timeout to prevent indefinite hangs
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => {
    timeoutController.abort();
  }, 18000);

  if (signal) {
    if (signal.aborted) {
      timeoutController.abort();
    } else {
      signal.addEventListener('abort', () => timeoutController.abort(), { once: true });
    }
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        message: message || '',
        conversation_id: conversationId || null,
        idempotency_key: resolvedIdempotencyKey,
        attachments: attachments && attachments.length > 0 ? attachments : undefined,
        images: attachments
          ? attachments.filter((a) => a.type === 'image' && a.url).map((a) => a.url)
          : undefined,
      }),
      signal: timeoutController.signal,
    });
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (signal?.aborted) {
      throw err;
    }
    if (timeoutController.signal.aborted) {
      const timeoutMsg = 'AI connection timed out after 18s waiting for model response. Please try again.';
      callbacks?.onError?.(timeoutMsg);
      throw new Error(timeoutMsg);
    }
    const isNetworkError =
      err instanceof TypeError &&
      (err.message.includes('fetch') || err.message.includes('NetworkError'));
    const friendlyMsg = isNetworkError
      ? `Failed to reach backend API at ${API_BASE_URL}. Verify backend service is deployed, online, and CORS is permitted.`
      : err?.message || 'Chat request failed';
    callbacks?.onError?.(friendlyMsg);
    throw new Error(friendlyMsg);
  }

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

  clearTimeout(timeoutId);
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

        let parsed: any = null;
        try {
          parsed = JSON.parse(currentData);
        } catch {
          // Plain text fallback
        }

        if (currentEvent === 'metadata' && parsed) {
          callbacks?.onMetadata?.(parsed);
        } else if (currentEvent === 'token') {
          callbacks?.onToken?.(parsed?.text ?? currentData);
        } else if (currentEvent === 'done' && parsed) {
          callbacks?.onDone?.(parsed);
        } else if (currentEvent === 'error') {
          const errorMsg = parsed?.detail || currentData || 'Stream error occurred';
          callbacks?.onError?.(errorMsg);
          throw new Error(errorMsg);
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

