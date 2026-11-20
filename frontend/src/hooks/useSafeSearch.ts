/**
 * Safe search params hook for AUREN.
 * Returns TanStack Router search params if within a RouterProvider,
 * or safely falls back to window.location.search / empty object when rendered in isolated unit tests.
 */

import { useSearch } from '@tanstack/react-router';

export function useSafeSearch<T = Record<string, any>>(): Partial<T> {
  try {
    return (useSearch({ strict: false } as any) as Partial<T>) || {};
  } catch {
    if (typeof window !== 'undefined' && window.location?.search) {
      const params = new URLSearchParams(window.location.search);
      const res: Record<string, any> = {};
      params.forEach((v, k) => {
        res[k] = v;
      });
      return res as Partial<T>;
    }
    return {};
  }
}
