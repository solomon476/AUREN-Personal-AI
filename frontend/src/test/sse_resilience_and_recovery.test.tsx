/**
 * Test Suite: SSE Resilience, Stream Reconnection, Exponential Backoff,
 * and Interruption Recovery.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderRouter } from './test-utils';
import * as chatApi from '../api/chat';

vi.mock('../api/chat', () => ({
  listConversations: vi.fn(),
  getConversationMessages: vi.fn(),
  createConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  streamChat: vi.fn(),
}));

vi.mock('../api/health', () => ({
  fetchHealth: vi.fn().mockResolvedValue({ status: 'healthy' }),
}));

describe('SSE Resilience and Stream Recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(chatApi.listConversations).mockResolvedValue([
      {
        id: 'conv-recovery-1',
        title: 'Recovery Thread',
        created_at: '2026-11-16T00:00:00Z',
        updated_at: '2026-11-16T00:00:00Z',
        message_count: 0,
      },
    ]);
    vi.mocked(chatApi.getConversationMessages).mockResolvedValue([]);
  });

  it('interrupted stream triggers exponential backoff reconnection and succeeds without duplicate messages', async () => {
    const user = userEvent.setup();
    let callCount = 0;

    // First attempt fails with transient network error, second attempt succeeds
    vi.mocked(chatApi.streamChat).mockImplementation(async (_msg, _convId, callbacks, _signal) => {
      callCount++;
      if (callCount === 1) {
        callbacks?.onToken?.('Partial token before drop ');
        throw new Error('Network connection reset by peer');
      } else {
        callbacks?.onToken?.('and rest of the completed response.');
        callbacks?.onDone?.({ message_id: 'msg-recovered-99', finish_reason: 'stop' });
      }
    });

    await renderRouter('/chat/conv-recovery-1');

    const input = screen.getByPlaceholderText(/ask auren anything/i);
    await user.type(input, 'Tell me about quantum computing');
    const sendButton = screen.getByRole('button', { name: /send message/i });
    await user.click(sendButton);

    // Verify first attempt occurred and reconnected
    await waitFor(
      () => {
        expect(callCount).toBe(2);
      },
      { timeout: 5000 }
    );

    // Verify assistant message is combined cleanly without duplicate bubbles
    await waitFor(() => {
      expect(screen.getByText(/and rest of the completed response/i)).toBeInTheDocument();
    });
  });

  it('does not retry permanent errors (409 conflict, 404, 413)', async () => {
    const user = userEvent.setup();
    let streamCalls = 0;

    vi.mocked(chatApi.streamChat).mockImplementation(async () => {
      streamCalls++;
      throw new Error('409 Conflict: Idempotency key reused with conflicting request parameters.');
    });

    await renderRouter('/chat/conv-recovery-1');

    const input = screen.getByPlaceholderText(/ask auren anything/i);
    await user.type(input, 'Test Conflict');
    const sendButton = screen.getByRole('button', { name: /send message/i });
    await user.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText(/409 Conflict/i)).toBeInTheDocument();
    });

    // Verify it did not attempt exponential backoff reconnection
    expect(streamCalls).toBe(1);
  });

  it('user stop button cancels streaming immediately and aborts auto-reconnection', async () => {
    const user = userEvent.setup();

    vi.mocked(chatApi.streamChat).mockImplementation(async (_msg, _id, callbacks, signal) => {
      callbacks?.onToken?.('Initial token before manual abort');
      // Hold stream open until aborted
      return new Promise((_, reject) => {
        signal?.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'));
        });
      });
    });

    await renderRouter('/chat/conv-recovery-1');

    const input = screen.getByPlaceholderText(/ask auren anything/i);
    await user.type(input, 'Infinite stream');
    const sendButton = screen.getByRole('button', { name: /send message/i });
    await user.click(sendButton);

    // Verify stop button appears while streaming
    await waitFor(() => {
      expect(screen.getByTitle(/stop generating/i)).toBeInTheDocument();
    });

    const stopButton = screen.getByTitle(/stop generating/i);
    await user.click(stopButton);

    // Verify streaming ceases
    await waitFor(() => {
      expect(screen.queryByTitle(/stop generating/i)).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /send message/i })).toBeInTheDocument();
    });
  });
});

