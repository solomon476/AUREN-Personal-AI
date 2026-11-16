/**
 * TanStack Query hooks for Conversation management.
 * Manages caching, background fetching, and mutation invalidation.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listConversations,
  createConversation,
  renameConversation,
  deleteConversation,
  Conversation,
} from '../api/chat';

export const conversationKeys = {
  all: ['conversations'] as const,
  lists: () => [...conversationKeys.all, 'list'] as const,
  list: (userId: string | undefined) => [...conversationKeys.lists(), userId ?? 'anonymous'] as const,
  details: () => [...conversationKeys.all, 'detail'] as const,
  detail: (userId: string | undefined, id: string | undefined) =>
    [...conversationKeys.details(), userId ?? 'anonymous', id ?? 'none'] as const,
};

export function useConversations(userId: string | undefined) {
  return useQuery({
    queryKey: conversationKeys.list(userId),
    queryFn: async (): Promise<Conversation[]> => {
      if (!userId) return [];
      return listConversations();
    },
    enabled: Boolean(userId),
  });
}

export function useCreateConversation(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (title?: string): Promise<Conversation> => {
      return createConversation(title);
    },
    onSuccess: (newConv) => {
      // Invalidate the conversations list to trigger fresh fetch with new item
      queryClient.invalidateQueries({
        queryKey: conversationKeys.list(userId),
      });

      // Optimistically update the list if desired
      queryClient.setQueryData<Conversation[]>(
        conversationKeys.list(userId),
        (old) => (old ? [newConv, ...old] : [newConv])
      );
    },
  });
}

export function useRenameConversation(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      conversationId,
      title,
    }: {
      conversationId: string;
      title: string;
    }): Promise<Conversation> => {
      return renameConversation(conversationId, title);
    },
    onSuccess: (updatedConv) => {
      queryClient.invalidateQueries({
        queryKey: conversationKeys.list(userId),
      });

      queryClient.setQueryData<Conversation[]>(
        conversationKeys.list(userId),
        (old) => (old ? old.map((c) => (c.id === updatedConv.id ? updatedConv : c)) : [updatedConv])
      );
    },
  });
}

export function useDeleteConversation(userId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (conversationId: string): Promise<string> => {
      await deleteConversation(conversationId);
      return conversationId;
    },
    onSuccess: (deletedId) => {
      queryClient.invalidateQueries({
        queryKey: conversationKeys.list(userId),
      });

      queryClient.setQueryData<Conversation[]>(
        conversationKeys.list(userId),
        (old) => (old ? old.filter((c) => c.id !== deletedId) : [])
      );

      queryClient.removeQueries({
        queryKey: ['messages', userId ?? 'anonymous', deletedId],
      });
    },
  });
}
