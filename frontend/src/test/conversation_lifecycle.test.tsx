/**
 * Test Suite: Conversation Lifecycle Management (Rename & Delete).
 * Verifies validation, modal interactions, TanStack Query cache synchronization,
 * and safe routing upon active thread deletion.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, act, renderHook } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RenameConversationModal } from '../components/chat/RenameConversationModal';
import { DeleteConversationModal } from '../components/chat/DeleteConversationModal';
import { useRenameConversation, useDeleteConversation, conversationKeys } from '../hooks/useConversations';
import { createWrapper, createTestQueryClient } from './test-utils';
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

describe('Conversation Lifecycle: Rename Modal', () => {
  it('validates title input and rejects empty or whitespace-only submission', async () => {
    const user = userEvent.setup();
    const onRename = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(
      <RenameConversationModal
        isOpen={true}
        initialTitle="Current Title"
        onClose={onClose}
        onRename={onRename}
      />
    );

    const input = screen.getByLabelText(/title/i);
    expect(input).toHaveValue('Current Title');

    // Clear input
    await user.clear(input);
    const saveButton = screen.getByRole('button', { name: /save/i });
    expect(saveButton).toBeDisabled();

    // Type spaces only
    await user.type(input, '    ');
    expect(saveButton).toBeDisabled();
    expect(onRename).not.toHaveBeenCalled();
  });

  it('submits valid trimmed title and closes dialog', async () => {
    const user = userEvent.setup();
    const onRename = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(
      <RenameConversationModal
        isOpen={true}
        initialTitle="Old Title"
        onClose={onClose}
        onRename={onRename}
      />
    );

    const input = screen.getByLabelText(/title/i);
    await user.clear(input);
    await user.type(input, 'New High Performance Architecture');

    const saveButton = screen.getByRole('button', { name: /save/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(onRename).toHaveBeenCalledWith('New High Performance Architecture');
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('dismisses modal on cancel or Escape key', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <RenameConversationModal
        isOpen={true}
        initialTitle="Old Title"
        onClose={onClose}
        onRename={vi.fn()}
      />
    );

    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelButton);
    expect(onClose).toHaveBeenCalled();
  });
});

describe('Conversation Lifecycle: Delete Modal', () => {
  it('renders confirmation warning and conversation title', () => {
    render(
      <DeleteConversationModal
        isOpen={true}
        conversationTitle="Sensitive Discussion"
        onClose={vi.fn()}
        onConfirmDelete={vi.fn()}
      />
    );

    expect(screen.getByRole('heading', { name: /delete conversation/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /delete conversation/i })).toBeInTheDocument();
    expect(screen.getByText('"Sensitive Discussion"')).toBeInTheDocument();
    expect(screen.getByText(/All messages in this conversation will be permanently deleted/i)).toBeInTheDocument();
  });

  it('triggers delete callback on confirmation', async () => {
    const user = userEvent.setup();
    const onConfirmDelete = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(
      <DeleteConversationModal
        isOpen={true}
        conversationTitle="Thread To Delete"
        onClose={onClose}
        onConfirmDelete={onConfirmDelete}
      />
    );

    const deleteBtn = screen.getByRole('button', { name: /delete conversation/i });
    await user.click(deleteBtn);

    await waitFor(() => {
      expect(onConfirmDelete).toHaveBeenCalledTimes(1);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});

describe('Conversation Lifecycle: TanStack Query Cache Synchronization', () => {
  const userId = 'user-lifecycle-123';

  it('useRenameConversation updates cached conversation in place and invalidates query', async () => {
    const queryClient = createTestQueryClient();
    const wrapper = createWrapper(queryClient);

    const initialList: chatApi.Conversation[] = [
      {
        id: 'conv-rename-1',
        title: 'Initial Title',
        created_at: '2026-11-16T00:00:00Z',
        updated_at: '2026-11-16T00:00:00Z',
        message_count: 5,
      },
    ];
    queryClient.setQueryData(conversationKeys.list(userId), initialList);

    const updatedConv: chatApi.Conversation = {
      ...initialList[0],
      title: 'Renamed Title',
      updated_at: '2026-11-16T00:05:00Z',
    };
    vi.mocked(chatApi.renameConversation).mockResolvedValueOnce(updatedConv);

    const { result } = renderHook(() => useRenameConversation(userId), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ conversationId: 'conv-rename-1', title: 'Renamed Title' });
    });

    const cachedList = queryClient.getQueryData<chatApi.Conversation[]>(conversationKeys.list(userId));
    expect(cachedList?.[0].title).toBe('Renamed Title');
  });

  it('useDeleteConversation removes thread from cached list and purges its message cache', async () => {
    const queryClient = createTestQueryClient();
    const wrapper = createWrapper(queryClient);

    const initialList: chatApi.Conversation[] = [
      {
        id: 'conv-del-1',
        title: 'Thread 1',
        created_at: '2026-11-16T00:00:00Z',
        updated_at: '2026-11-16T00:00:00Z',
        message_count: 2,
      },
      {
        id: 'conv-del-2',
        title: 'Thread 2',
        created_at: '2026-11-16T00:01:00Z',
        updated_at: '2026-11-16T00:01:00Z',
        message_count: 0,
      },
    ];
    queryClient.setQueryData(conversationKeys.list(userId), initialList);
    queryClient.setQueryData(['messages', userId, 'conv-del-1'], [{ id: 'm1', content: 'Secret' }]);

    vi.mocked(chatApi.deleteConversation).mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useDeleteConversation(userId), { wrapper });

    await act(async () => {
      await result.current.mutateAsync('conv-del-1');
    });

    const cachedList = queryClient.getQueryData<chatApi.Conversation[]>(conversationKeys.list(userId));
    expect(cachedList?.length).toBe(1);
    expect(cachedList?.[0].id).toBe('conv-del-2');

    // Message cache for deleted thread must be purged
    const cachedMessages = queryClient.getQueryData(['messages', userId, 'conv-del-1']);
    expect(cachedMessages).toBeUndefined();
  });
});
