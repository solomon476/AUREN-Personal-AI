/**
 * TanStack Query hooks for Memory Management and Epistemic Verification.
 * Manages caching, query invalidation, and server-state synchronization.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listMemories,
  getMemory,
  createMemory,
  confirmMemory,
  rejectMemory,
  correctMemory,
  archiveMemory,
  restoreMemory,
  outdateMemory,
  getMessageContext,
  Memory,
  MemoryListResponse,
  MemoryFilterParams,
  CreateMemoryPayload,
  CorrectMemoryPayload,
  MessageContextResponse,
} from '../api/memories';

export const memoryKeys = {
  all: ['memories'] as const,
  lists: () => [...memoryKeys.all, 'list'] as const,
  list: (userId: string | undefined, params: MemoryFilterParams) =>
    [...memoryKeys.lists(), userId ?? 'anonymous', params] as const,
  details: () => [...memoryKeys.all, 'detail'] as const,
  detail: (userId: string | undefined, id: string | undefined) =>
    [...memoryKeys.details(), userId ?? 'anonymous', id ?? 'none'] as const,
  context: (userId: string | undefined, conversationId: string | undefined, messageId: string | undefined) =>
    ['message-context', userId ?? 'anonymous', conversationId ?? 'none', messageId ?? 'none'] as const,
};

export function useMemories(userId: string | undefined, params: MemoryFilterParams = {}) {
  return useQuery({
    queryKey: memoryKeys.list(userId, params),
    queryFn: async (): Promise<MemoryListResponse> => {
      if (!userId) return { items: [], total: 0, page: 1, page_size: 20, has_more: false };
      return listMemories(params);
    },
    enabled: Boolean(userId),
  });
}

export function useMemory(userId: string | undefined, memoryId: string | undefined) {
  return useQuery({
    queryKey: memoryKeys.detail(userId, memoryId),
    queryFn: async (): Promise<Memory | null> => {
      if (!userId || !memoryId) return null;
      return getMemory(memoryId);
    },
    enabled: Boolean(userId && memoryId),
  });
}

export function useCreateMemory(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: CreateMemoryPayload): Promise<Memory> => {
      return createMemory(payload);
    },
    onSuccess: (newMemory) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.setQueryData(memoryKeys.detail(userId, newMemory.id), newMemory);
    },
  });
}

export function useConfirmMemory(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (memoryId: string): Promise<Memory> => {
      return confirmMemory(memoryId);
    },
    onSuccess: (updatedMemory) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.setQueryData(memoryKeys.detail(userId, updatedMemory.id), updatedMemory);
    },
  });
}

export function useRejectMemory(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (memoryId: string): Promise<Memory> => {
      return rejectMemory(memoryId);
    },
    onSuccess: (updatedMemory) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.setQueryData(memoryKeys.detail(userId, updatedMemory.id), updatedMemory);
    },
  });
}

export function useCorrectMemory(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      memoryId,
      payload,
    }: {
      memoryId: string;
      payload: CorrectMemoryPayload;
    }): Promise<Memory> => {
      return correctMemory(memoryId, payload);
    },
    onSuccess: (newMemory, variables) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: memoryKeys.detail(userId, variables.memoryId) });
      queryClient.setQueryData(memoryKeys.detail(userId, newMemory.id), newMemory);
    },
  });
}

export function useArchiveMemory(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (memoryId: string): Promise<Memory> => {
      return archiveMemory(memoryId);
    },
    onSuccess: (updatedMemory) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.setQueryData(memoryKeys.detail(userId, updatedMemory.id), updatedMemory);
    },
  });
}

export function useRestoreMemory(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (memoryId: string): Promise<Memory> => {
      return restoreMemory(memoryId);
    },
    onSuccess: (updatedMemory) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.setQueryData(memoryKeys.detail(userId, updatedMemory.id), updatedMemory);
    },
  });
}

export function useOutdateMemory(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (memoryId: string): Promise<Memory> => {
      return outdateMemory(memoryId);
    },
    onSuccess: (updatedMemory) => {
      queryClient.invalidateQueries({ queryKey: memoryKeys.lists() });
      queryClient.setQueryData(memoryKeys.detail(userId, updatedMemory.id), updatedMemory);
    },
  });
}

export function useMessageContext(
  userId: string | undefined,
  conversationId: string | undefined,
  messageId: string | undefined
) {
  return useQuery({
    queryKey: memoryKeys.context(userId, conversationId, messageId),
    queryFn: async (): Promise<MessageContextResponse> => {
      if (!conversationId || !messageId) {
        return { message_id: '', conversation_id: '', retrieved_memories: [], memory_count: 0 };
      }
      return getMessageContext(conversationId, messageId);
    },
    enabled: Boolean(userId && conversationId && messageId),
  });
}
