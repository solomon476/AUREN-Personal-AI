/**
 * Test Suite 5: TanStack Query Caching, Invalidation, and Logout Lifecycle.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createWrapper, createTestQueryClient } from './test-utils';
import { useConversations, useCreateConversation, conversationKeys } from '../hooks/useConversations';
import { useConversationMessages, messageKeys } from '../hooks/useConversationMessages';
import { useTasks, PRODUCTIVITY_KEYS } from '../hooks/useProductivity';
import { clearUserDataCache } from '../lib/queryClient';
import * as chatApi from '../api/chat';
import * as productivityApi from '../api/productivity';

vi.mock('../api/chat', () => ({
  listConversations: vi.fn(),
  getConversationMessages: vi.fn(),
  createConversation: vi.fn(),
  streamChat: vi.fn(),
}));

vi.mock('../api/productivity', () => ({
  getTasks: vi.fn(),
  getProjects: vi.fn(),
  getGoals: vi.fn(),
  getProductivityDashboard: vi.fn(),
}));

describe('TanStack Query Caching & Lifecycle Management', () => {
  const userA = 'user-uuid-aaa';
  const userB = 'user-uuid-bbb';

  const mockConversationsA: chatApi.Conversation[] = [
    {
      id: 'conv-a1',
      title: 'User A Thread',
      created_at: '2026-11-16T00:00:00Z',
      updated_at: '2026-11-16T00:00:00Z',
      message_count: 1,
    },
  ];

  const mockConversationsB: chatApi.Conversation[] = [
    {
      id: 'conv-b1',
      title: 'User B Thread',
      created_at: '2026-11-16T00:01:00Z',
      updated_at: '2026-11-16T00:01:00Z',
      message_count: 5,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('caches conversation list per user identity to prevent cross-user data leakage', async () => {
    const queryClient = createTestQueryClient();
    const wrapper = createWrapper(queryClient);

    vi.mocked(chatApi.listConversations).mockResolvedValueOnce(mockConversationsA);

    // 1. Fetch User A conversations
    const { result: resultA } = renderHook(() => useConversations(userA), { wrapper });

    await waitFor(() => {
      expect(resultA.current.isSuccess).toBe(true);
      expect(resultA.current.data).toEqual(mockConversationsA);
    });
    expect(chatApi.listConversations).toHaveBeenCalledTimes(1);

    // 2. Fetch User B conversations (different user)
    vi.mocked(chatApi.listConversations).mockResolvedValueOnce(mockConversationsB);
    const { result: resultB } = renderHook(() => useConversations(userB), { wrapper });

    await waitFor(() => {
      expect(resultB.current.isSuccess).toBe(true);
      expect(resultB.current.data).toEqual(mockConversationsB);
    });
    expect(chatApi.listConversations).toHaveBeenCalledTimes(2);

    // 3. Verify User A data is cached separately from User B in queryClient
    const cachedA = queryClient.getQueryData(conversationKeys.list(userA));
    const cachedB = queryClient.getQueryData(conversationKeys.list(userB));
    expect(cachedA).toEqual(mockConversationsA);
    expect(cachedB).toEqual(mockConversationsB);
    expect(cachedA).not.toEqual(cachedB);
  });

  it('useCreateConversation mutation invalidates and prepends new conversation to cache', async () => {
    const queryClient = createTestQueryClient();
    const wrapper = createWrapper(queryClient);

    vi.mocked(chatApi.listConversations).mockResolvedValueOnce(mockConversationsA);
    const { result: convResult } = renderHook(() => useConversations(userA), { wrapper });

    await waitFor(() => {
      expect(convResult.current.isSuccess).toBe(true);
      expect(convResult.current.data?.length).toBe(1);
    });

    const newCreatedConv: chatApi.Conversation = {
      id: 'conv-a2',
      title: 'Newly Created Thread',
      created_at: '2026-11-16T00:02:00Z',
      updated_at: '2026-11-16T00:02:00Z',
      message_count: 0,
    };
    vi.mocked(chatApi.createConversation).mockResolvedValueOnce(newCreatedConv);

    // Trigger mutation
    const { result: mutationResult } = renderHook(() => useCreateConversation(userA), { wrapper });
    await act(async () => {
      await mutationResult.current.mutateAsync('Newly Created Thread');
    });

    // Verify cache now contains the new conversation prepended
    const updatedCache = queryClient.getQueryData<chatApi.Conversation[]>(conversationKeys.list(userA));
    expect(updatedCache).toBeDefined();
    expect(updatedCache?.length).toBe(2);
    expect(updatedCache?.[0].id).toBe('conv-a2');
  });

  it('useConversationMessages caches messages scoped strictly by user and conversation ID', async () => {
    const queryClient = createTestQueryClient();
    const wrapper = createWrapper(queryClient);

    const mockMessages: chatApi.ChatMessage[] = [
      {
        id: 'msg-cached-1',
        conversation_id: 'conv-a1',
        role: 'user',
        content: 'Cached message query content',
        created_at: '2026-11-16T00:00:00Z',
      },
    ];
    vi.mocked(chatApi.getConversationMessages).mockResolvedValueOnce(mockMessages);

    const { result } = renderHook(() => useConversationMessages(userA, 'conv-a1'), { wrapper });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
      expect(result.current.data).toEqual(mockMessages);
    });

    const cachedMessages = queryClient.getQueryData(messageKeys.conversation(userA, 'conv-a1'));
    expect(cachedMessages).toEqual(mockMessages);
  });

  it('clearUserDataCache completely clears queries on logout to prevent data leakage', async () => {
    const { queryClient: activeClient } = await import('../lib/queryClient');

    // Populate active queryClient with sensitive data
    activeClient.setQueryData(conversationKeys.list(userA), mockConversationsA);
    activeClient.setQueryData(messageKeys.conversation(userA, 'conv-a1'), [{ id: 'm1', content: 'Secret' }]);
    activeClient.setQueryData(PRODUCTIVITY_KEYS.tasks(userA), [{ id: 't1', title: 'User A Secret Task' }]);
    activeClient.setQueryData(PRODUCTIVITY_KEYS.dashboard(userA), { active_tasks_count: 1 });

    expect(activeClient.getQueryData(conversationKeys.list(userA))).toBeDefined();
    expect(activeClient.getQueryData(messageKeys.conversation(userA, 'conv-a1'))).toBeDefined();
    expect(activeClient.getQueryData(PRODUCTIVITY_KEYS.tasks(userA))).toBeDefined();
    expect(activeClient.getQueryData(PRODUCTIVITY_KEYS.dashboard(userA))).toBeDefined();

    // Call clearUserDataCache() as invoked on sign out
    clearUserDataCache();

    // Verify all queries are purged including productivity cache
    expect(activeClient.getQueryData(conversationKeys.list(userA))).toBeUndefined();
    expect(activeClient.getQueryData(messageKeys.conversation(userA, 'conv-a1'))).toBeUndefined();
    expect(activeClient.getQueryData(PRODUCTIVITY_KEYS.tasks(userA))).toBeUndefined();
    expect(activeClient.getQueryData(PRODUCTIVITY_KEYS.dashboard(userA))).toBeUndefined();
    expect(activeClient.getQueryCache().getAll().length).toBe(0);
  });

  it('scopes productivity query keys by authenticated user identity to prevent cross-account cache leakage', async () => {
    const queryClient = createTestQueryClient();
    const wrapper = createWrapper(queryClient);

    const mockTasksA: productivityApi.TaskListResponse = {
      items: [
        {
          id: 'task-a1',
          user_id: userA,
          title: 'User A Confidential Task',
          status: 'todo',
          priority: 'urgent',
          tags: [],
          created_at: '2026-11-17T00:00:00Z',
          updated_at: '2026-11-17T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    };

    const mockTasksB: productivityApi.TaskListResponse = {
      items: [
        {
          id: 'task-b1',
          user_id: userB,
          title: 'User B Public Task',
          status: 'completed',
          priority: 'low',
          tags: [],
          created_at: '2026-11-17T00:00:00Z',
          updated_at: '2026-11-17T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    };

    vi.mocked(productivityApi.getTasks).mockResolvedValueOnce(mockTasksA);

    // 1. Fetch User A tasks
    const { result: resultA } = renderHook(() => useTasks({}, userA), { wrapper });
    await waitFor(() => {
      expect(resultA.current.isSuccess).toBe(true);
      expect(resultA.current.data).toEqual(mockTasksA);
    });

    // 2. Fetch User B tasks
    vi.mocked(productivityApi.getTasks).mockResolvedValueOnce(mockTasksB);
    const { result: resultB } = renderHook(() => useTasks({}, userB), { wrapper });
    await waitFor(() => {
      expect(resultB.current.isSuccess).toBe(true);
      expect(resultB.current.data).toEqual(mockTasksB);
    });

    // 3. Verify User A and User B query cache keys are strictly isolated
    const cachedTasksA = queryClient.getQueryData([...PRODUCTIVITY_KEYS.tasks(userA), {}]);
    const cachedTasksB = queryClient.getQueryData([...PRODUCTIVITY_KEYS.tasks(userB), {}]);

    expect(cachedTasksA).toEqual(mockTasksA);
    expect(cachedTasksB).toEqual(mockTasksB);
    expect(cachedTasksA).not.toEqual(cachedTasksB);
  });
});
