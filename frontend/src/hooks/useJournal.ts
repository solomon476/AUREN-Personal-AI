/**
 * TanStack Query hooks for Private Journaling state management.
 */

import { useContext } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AuthContext } from '../context/AuthContext';
import {
  createJournalEntry,
  deleteJournalEntry,
  getJournalEntry,
  listJournalEntries,
  updateJournalEntry,
  JournalEntryCreate,
  JournalEntryUpdate,
  JournalListParams,
  JournalEntryListResponse,
} from '../api/journal';

export function useCurrentUserId(explicitUserId?: string): string {
  const auth = useContext(AuthContext);
  return explicitUserId ?? auth?.user?.id ?? 'anonymous';
}

export const JOURNAL_KEYS = {
  all: ['journal'] as const,
  lists: (userId?: string) => ['journal', 'list', userId ?? 'anonymous'] as const,
  list: (params: JournalListParams | undefined, userId?: string) =>
    ['journal', 'list', userId ?? 'anonymous', params] as const,
  entry: (id: string, userId?: string) => ['journal', 'entry', userId ?? 'anonymous', id] as const,
};

export function useJournalEntries(params?: JournalListParams, userId?: string) {
  const currentUserId = useCurrentUserId(userId);
  const isAuthenticated = currentUserId !== 'anonymous';

  return useQuery({
    queryKey: JOURNAL_KEYS.list(params, currentUserId),
    queryFn: async (): Promise<JournalEntryListResponse> => {
      if (!isAuthenticated) {
        return { items: [], total: 0, page: 1, page_size: 20, has_more: false };
      }
      return listJournalEntries(params);
    },
    enabled: isAuthenticated,
    staleTime: 1000 * 30,
  });
}

export function useJournalEntry(entryId?: string, userId?: string) {
  const currentUserId = useCurrentUserId(userId);
  const isAuthenticated = currentUserId !== 'anonymous';

  return useQuery({
    queryKey: JOURNAL_KEYS.entry(entryId || '', currentUserId),
    queryFn: () => getJournalEntry(entryId!),
    enabled: Boolean(entryId && isAuthenticated),
  });
}

export function useCreateJournalEntry(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);

  return useMutation({
    mutationFn: (payload: JournalEntryCreate) => createJournalEntry(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: JOURNAL_KEYS.lists(currentUserId) });
    },
  });
}

export function useUpdateJournalEntry(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);

  return useMutation({
    mutationFn: ({ entryId, payload }: { entryId: string; payload: JournalEntryUpdate }) =>
      updateJournalEntry(entryId, payload),
    onSuccess: (_, { entryId }) => {
      queryClient.invalidateQueries({ queryKey: JOURNAL_KEYS.lists(currentUserId) });
      queryClient.invalidateQueries({ queryKey: JOURNAL_KEYS.entry(entryId, currentUserId) });
    },
  });
}

export function useDeleteJournalEntry(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);

  return useMutation({
    mutationFn: (entryId: string) => deleteJournalEntry(entryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: JOURNAL_KEYS.lists(currentUserId) });
    },
  });
}
