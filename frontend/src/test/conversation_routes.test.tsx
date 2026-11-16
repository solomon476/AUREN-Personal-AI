/**
 * Test Suite 3: Conversation Route Handling & Lifecycle.
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
  streamChat: vi.fn(),
}));

vi.mock('../api/health', () => ({
  fetchHealth: vi.fn().mockResolvedValue({ status: 'healthy' }),
}));

describe('Conversation Route Handling', () => {
  const mockConversations: chatApi.Conversation[] = [
    {
      id: 'conv-alpha-1',
      title: 'Alpha Thread',
      created_at: '2026-11-16T00:00:00Z',
      updated_at: '2026-11-16T00:00:00Z',
      message_count: 2,
    },
    {
      id: 'conv-beta-2',
      title: 'Beta Thread',
      created_at: '2026-11-16T00:01:00Z',
      updated_at: '2026-11-16T00:01:00Z',
      message_count: 0,
    },
  ];

  const mockAlphaMessages: chatApi.ChatMessage[] = [
    {
      id: 'msg-1',
      conversation_id: 'conv-alpha-1',
      role: 'user',
      content: 'Hello AUREN from test',
      created_at: '2026-11-16T00:00:01Z',
    },
    {
      id: 'msg-2',
      conversation_id: 'conv-alpha-1',
      role: 'assistant',
      content: 'Greetings. Ready to assist.',
      created_at: '2026-11-16T00:00:02Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(chatApi.listConversations).mockResolvedValue(mockConversations);
    vi.mocked(chatApi.getConversationMessages).mockImplementation(async (convId) => {
      if (convId === 'conv-alpha-1') return mockAlphaMessages;
      if (convId === 'conv-beta-2') return [];
      throw new Error('Conversation not found or access denied.');
    });
  });

  it('direct navigation to /chat/$conversationId fetches and displays its messages', async () => {
    await renderRouter('/chat/conv-alpha-1');

    await waitFor(() => {
      expect(screen.getAllByText('Alpha Thread').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Hello AUREN from test')).toBeInTheDocument();
      expect(screen.getByText('Greetings. Ready to assist.')).toBeInTheDocument();
    });
  });

  it('clicking a conversation thread updates the URL and message list', async () => {
    const user = userEvent.setup();
    const { history } = await renderRouter('/chat/conv-beta-2');

    await waitFor(() => {
      expect(screen.getAllByText('Beta Thread').length).toBeGreaterThanOrEqual(1);
    });

    // Click Alpha Thread in the sidebar
    const alphaButton = screen.getByRole('button', { name: /alpha thread/i });
    await user.click(alphaButton);

    await waitFor(() => {
      expect(history.location.pathname).toBe('/chat/conv-alpha-1');
      expect(screen.getByText('Hello AUREN from test')).toBeInTheDocument();
    });
  });

  it('safely handles non-existent or inaccessible conversation IDs with recovery action', async () => {
    await renderRouter('/chat/invalid-unknown-uuid');

    await waitFor(() => {
      expect(screen.getByText(/Conversation not found or access denied/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /return to chat/i })).toBeInTheDocument();
    });
  });
});
