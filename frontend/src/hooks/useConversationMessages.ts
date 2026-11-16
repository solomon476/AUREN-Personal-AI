/**
 * TanStack Query hooks for Conversation Messages history.
 * Scoped strictly by user identity and conversation ID to prevent data bleed.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getConversationMessages, ChatMessage } from '../api/chat';

export const messageKeys = {
  all: ['messages'] as const,
  conversation: (userId: string | undefined, conversationId: string | undefined) =>
    [...messageKeys.all, userId ?? 'anonymous', conversationId ?? 'none'] as const,
};

export function useConversationMessages(
  userId: string | undefined,
  conversationId: string | undefined
) {
  return useQuery({
    queryKey: messageKeys.conversation(userId, conversationId),
    queryFn: async (): Promise<ChatMessage[]> => {
      if (!userId || !conversationId) return [];
      return getConversationMessages(conversationId);
    },
    enabled: Boolean(userId && conversationId),
  });
}

export function useInvalidateMessages() {
  const queryClient = useQueryClient();
  return (userId: string | undefined, conversationId: string | undefined) => {
    queryClient.invalidateQueries({
      queryKey: messageKeys.conversation(userId, conversationId),
    });
  };
}
