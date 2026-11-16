/**
 * Test Suite: In-Chat Context Inspector Modal.
 * Verifies display of injected context memories, relevance scores,
 * journal isolation protections, and empty states.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContextInspectorModal } from '../components/chat/ContextInspectorModal';
import { createWrapper } from './test-utils';
import * as memoryApi from '../api/memories';

vi.mock('../api/memories', () => ({
  getMessageContext: vi.fn(),
}));

describe('Context Inspector Modal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders recorded context provenance with similarity scores and journal isolation notice', async () => {
    vi.mocked(memoryApi.getMessageContext).mockResolvedValue({
      message_id: 'msg-123',
      conversation_id: 'conv-456',
      model: 'gemini-1.5-pro',
      memory_count: 1,
      retrieved_memories: [
        {
          id: 'mem-999',
          content: 'User prefers functional TypeScript programming patterns.',
          memory_type: 'preference',
          category: 'technical',
          confirmation_status: 'confirmed',
          importance: 4,
          score: 0.89,
        },
      ],
    });

    render(
      <ContextInspectorModal
        isOpen={true}
        onClose={vi.fn()}
        conversationId="conv-456"
        messageId="msg-123"
        userId="user-test"
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('heading', { name: /context inspector & memory provenance/i })).toBeInTheDocument();
    expect(screen.getByText(/strict journal isolation/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/functional TypeScript programming patterns/i)).toBeInTheDocument();
      expect(screen.getByText('gemini-1.5-pro')).toBeInTheDocument();
      expect(screen.getByText('89%')).toBeInTheDocument();
      expect(screen.getByText('Confirmed')).toBeInTheDocument();
    });
  });

  it('displays empty state when no memories were injected into context', async () => {
    vi.mocked(memoryApi.getMessageContext).mockResolvedValue({
      message_id: 'msg-124',
      conversation_id: 'conv-456',
      model: 'mock-test-v1',
      memory_count: 0,
      retrieved_memories: [],
    });

    render(
      <ContextInspectorModal
        isOpen={true}
        onClose={vi.fn()}
        conversationId="conv-456"
        messageId="msg-124"
        userId="user-test"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByText('No Memories Injected into Context')).toBeInTheDocument();
      expect(screen.getByText(/AUREN answered this prompt without injecting persistent long-term memories/i)).toBeInTheDocument();
    });
  });

  it('closes dialog on close button click', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    vi.mocked(memoryApi.getMessageContext).mockResolvedValue({
      message_id: 'msg-125',
      conversation_id: 'conv-456',
      model: 'mock-test-v1',
      memory_count: 0,
      retrieved_memories: [],
    });

    render(
      <ContextInspectorModal
        isOpen={true}
        onClose={onClose}
        conversationId="conv-456"
        messageId="msg-125"
        userId="user-test"
      />,
      { wrapper: createWrapper() }
    );

    const closeButton = screen.getByRole('button', { name: /close dialog/i });
    await user.click(closeButton);

    expect(onClose).toHaveBeenCalled();
  });
});

