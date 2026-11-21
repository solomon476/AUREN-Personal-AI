/**
 * Integration Test Suite: Chat Connectivity, Network Diagnostics & Error Resilience.
 * Tests:
 * 1. StreamChat network error handling (Failed to fetch -> descriptive ApiError/NetworkError).
 * 2. Backend SSE error event handling (AI authentication failure, quota, internal errors).
 * 3. ChatView guest authentication enforcement (AuthModal triggered before doomed network calls).
 * 4. Non-retryable backend connection failure presentation.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderRouter } from './test-utils';
import { streamChat } from '../api/chat';
import * as chatApi from '../api/chat';

vi.mock('../api/health', () => ({
  fetchHealth: vi.fn().mockResolvedValue({ status: 'healthy' }),
}));

describe('Chat Connectivity and Error Handling', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe('streamChat API Network Diagnostics', () => {
    it('converts TypeError: Failed to fetch into descriptive backend unreachable error', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
      const onErrorMock = vi.fn();

      await expect(
        streamChat('Hello world', undefined, { onError: onErrorMock })
      ).rejects.toThrow(/Failed to reach backend API at/i);

      expect(onErrorMock).toHaveBeenCalledWith(
        expect.stringMatching(/Failed to reach backend API at/i)
      );
    });

    it('propagates HTTP error status details when backend returns non-ok response', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Invalid authentication credentials' }),
      } as unknown as Response);

      const onErrorMock = vi.fn();

      await expect(
        streamChat('Hello world', undefined, { onError: onErrorMock })
      ).rejects.toThrow('Invalid authentication credentials');

      expect(onErrorMock).toHaveBeenCalledWith('Invalid authentication credentials');
    });

    it('correctly dispatches and terminates stream on SSE error event from AI provider', async () => {
      const ssePayload = [
        'event: error',
        'data: {"detail": "The AI service is unavailable due to authentication configuration."}',
        '',
        '',
      ].join('\n');

      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(ssePayload));
          controller.close();
        },
      });

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        body: stream,
      } as unknown as Response);

      const onErrorMock = vi.fn();

      await expect(
        streamChat('Hello', 'conv-123', { onError: onErrorMock })
      ).rejects.toThrow(/The AI service is unavailable due to authentication configuration/i);

      expect(onErrorMock).toHaveBeenCalledWith(
        'The AI service is unavailable due to authentication configuration.'
      );
    });
  });

  describe('ChatView Guest State and Authentication Gates', () => {
    it('displays private authenticated assistant banner when user is not logged in', async () => {
      await renderRouter('/chat', { user: null });

      expect(
        screen.getByText(/Private Authenticated Assistant/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Sign in to chat with AUREN, access persistent dialogues, and leverage memory context/i)
      ).toBeInTheDocument();
    });

    it('opens AuthModal when guest clicks New Conversation', async () => {
      const user = userEvent.setup();
      await renderRouter('/chat', { user: null });

      const newConvBtn = screen.getByRole('button', { name: /new conversation/i });
      await user.click(newConvBtn);

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(screen.getByText(/Welcome Back to AUREN/i)).toBeInTheDocument();
      });
    });

    it('opens AuthModal and retains typed message when guest attempts to submit prompt', async () => {
      const user = userEvent.setup();
      await renderRouter('/chat', { user: null });

      const textarea = screen.getByPlaceholderText(/ask auren anything/i);
      await user.type(textarea, 'What are my top priorities today?');

      const sendBtn = screen.getByRole('button', { name: /send message/i });
      await user.click(sendBtn);

      // Verify AuthModal opened
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Verify the input text is not lost
      expect(textarea).toHaveValue('What are my top priorities today?');
    });
  });

  describe('ChatView Unreachable Backend Presentation', () => {
    it('immediately renders descriptive backend unreachable error without endless retries', async () => {
      const user = userEvent.setup();
      let streamCalls = 0;

      vi.spyOn(chatApi, 'streamChat').mockImplementation(async () => {
        streamCalls++;
        throw new Error('Failed to reach backend API at http://localhost:8000/api/v1. Verify backend service is deployed, online, and CORS is permitted.');
      });

      await renderRouter('/chat');

      const textarea = screen.getByPlaceholderText(/ask auren anything/i);
      await user.type(textarea, 'Hello assistant');

      const sendBtn = screen.getByRole('button', { name: /send message/i });
      await user.click(sendBtn);

      await waitFor(() => {
        expect(
          screen.getByText(/Failed to reach backend API at http:\/\/localhost:8000\/api\/v1/i)
        ).toBeInTheDocument();
      });

      // Assert non-retryable: only 1 attempt made, no backoff loop
      expect(streamCalls).toBe(1);
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  describe('Chat Attachments, Voice Notes & Empty Response Guard', () => {
    it('renders attach image and voice note recording buttons', async () => {
      await renderRouter('/chat');

      expect(screen.getByRole('button', { name: /attach image/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /record voice note/i })).toBeInTheDocument();
    });

    it('renders fallback retry card and hides Context Inspector when assistant response is empty', async () => {
      vi.spyOn(chatApi, 'getConversationMessages').mockResolvedValue([
        {
          id: 'user-msg-1',
          conversation_id: 'conv-1',
          role: 'user',
          content: 'Can we set the program now',
          created_at: new Date().toISOString(),
        },
        {
          id: 'assistant-msg-empty',
          conversation_id: 'conv-1',
          role: 'assistant',
          content: '', // Empty response bug from screenshot
          created_at: new Date().toISOString(),
        },
      ]);
      vi.spyOn(chatApi, 'listConversations').mockResolvedValue([
        {
          id: 'conv-1',
          title: 'My Program',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          message_count: 2,
        },
      ]);

      await renderRouter('/chat/conv-1');

      await waitFor(() => {
        expect(screen.getByText('Can we set the program now')).toBeInTheDocument();
        expect(screen.getByText(/Response could not be retrieved/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
        // Crucial: ensure empty response does NOT display Context Inspector button!
        expect(screen.queryByText(/Context Inspector/i)).not.toBeInTheDocument();
      });
    });

    it('renders image and audio attachments within conversation messages', async () => {
      vi.spyOn(chatApi, 'getConversationMessages').mockResolvedValue([
        {
          id: 'user-msg-attachments',
          conversation_id: 'conv-2',
          role: 'user',
          content: 'Here is my photo and voice memo',
          created_at: new Date().toISOString(),
          metadata: {
            attachments: [
              {
                type: 'image',
                url: 'https://images.example.com/photo.png',
                name: 'sample_photo.png',
              },
              {
                type: 'audio',
                url: 'https://audio.example.com/note.webm',
                duration: 5,
              },
            ],
          },
        },
      ]);
      vi.spyOn(chatApi, 'listConversations').mockResolvedValue([
        {
          id: 'conv-2',
          title: 'Multimedia Dialogue',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          message_count: 1,
        },
      ]);

      await renderRouter('/chat/conv-2');

      await waitFor(() => {
        const img = screen.getByAltText('sample_photo.png');
        expect(img).toBeInTheDocument();
        expect(img).toHaveAttribute('src', 'https://images.example.com/photo.png');
      });
    });
  });
});
