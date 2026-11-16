/**
 * Centralized TanStack Query Client configuration.
 * Enforces predictable caching, sensible retry policies, and secure cache invalidation.
 */

import { QueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/client';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 1000 * 60 * 2, // 2 minutes: prevents unnecessary refetches during active workflows
        gcTime: 1000 * 60 * 10,   // 10 minutes: keep inactive data in cache before garbage collection
        refetchOnWindowFocus: false, // Don't interrupt user during streaming or active interaction
        refetchOnReconnect: true,
        retry: (failureCount, error) => {
          // Do not retry client-side HTTP errors (4xx)
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return failureCount < 1;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export const queryClient = createQueryClient();

/**
 * Completely purge all cached user and resource data on sign out.
 * Prevents cross-user query cache leakage between sessions.
 */
export function clearUserDataCache(): void {
  queryClient.clear();
}
