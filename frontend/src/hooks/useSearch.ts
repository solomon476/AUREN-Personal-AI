/**
 * Phase 3C.5: TanStack Query hooks for Omnisearch & Reflective Intelligence.
 *
 * User-isolation is enforced at two levels:
 *   1. Query keys include the userId so each user's results occupy separate
 *      cache partitions. Switching accounts never serves stale data.
 *   2. The backend enforces auth.uid() ownership on every query.
 *
 * Journal entries are excluded from all results by backend design.
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query';
import {
  omnisearch,
  getReflectionInsights,
  getContradictions,
  getStaleness,
  getRelationships,
  OmnisearchParams,
  OmnisearchResponse,
  ReflectionInsightsResponse,
  SourceType,
  RelationshipsResponse,
} from '../api/search';

// ---------------------------------------------------------------------------
// Query key factories — user-scoped for cache isolation
// ---------------------------------------------------------------------------

export const searchKeys = {
  all: (userId: string | undefined) => ['search', userId ?? 'anonymous'] as const,
  query: (userId: string | undefined, params: OmnisearchParams) =>
    [...searchKeys.all(userId), 'query', params] as const,
};

export const reflectionKeys = {
  all: (userId: string | undefined) => ['reflection', userId ?? 'anonymous'] as const,
  insights: (userId: string | undefined) => [...reflectionKeys.all(userId), 'insights'] as const,
  contradictions: (userId: string | undefined) =>
    [...reflectionKeys.all(userId), 'contradictions'] as const,
  staleness: (userId: string | undefined) => [...reflectionKeys.all(userId), 'staleness'] as const,
  relationships: (userId: string | undefined, sourceType: SourceType, sourceId: string) =>
    [...reflectionKeys.all(userId), 'relationships', sourceType, sourceId] as const,
};

// ---------------------------------------------------------------------------
// Omnisearch hook
// ---------------------------------------------------------------------------

/**
 * Unified search hook. Returns results across all AUREN personal data entities.
 * Only fetches when query is non-empty and userId is present.
 */
export function useOmnisearch(
  userId: string | undefined,
  params: OmnisearchParams,
  options: { enabled?: boolean } = {}
) {
  const isEnabled = Boolean(userId) && params.q.trim().length > 0 && (options.enabled !== false);

  return useQuery<OmnisearchResponse>({
    queryKey: searchKeys.query(userId, params),
    queryFn: () => omnisearch(params),
    enabled: isEnabled,
    staleTime: 30_000,          // 30s — search results stay fresh for a short window
    placeholderData: keepPreviousData,
  });
}

// ---------------------------------------------------------------------------
// Reflection hooks
// ---------------------------------------------------------------------------

/**
 * Combined insights overview: contradiction count, staleness count, inferred link count.
 */
export function useReflectionInsights(userId: string | undefined) {
  return useQuery<ReflectionInsightsResponse>({
    queryKey: reflectionKeys.insights(userId),
    queryFn: () => getReflectionInsights(),
    enabled: Boolean(userId),
    staleTime: 60_000,          // 1 minute — reflection is relatively stable
  });
}

/**
 * Contradiction detection analysis.
 */
export function useContradictions(userId: string | undefined) {
  return useQuery({
    queryKey: reflectionKeys.contradictions(userId),
    queryFn: () => getContradictions(),
    enabled: Boolean(userId),
    staleTime: 60_000,
  });
}

/**
 * Staleness review items.
 */
export function useStaleness(userId: string | undefined) {
  return useQuery({
    queryKey: reflectionKeys.staleness(userId),
    queryFn: () => getStaleness(),
    enabled: Boolean(userId),
    staleTime: 60_000,
  });
}

/**
 * Cross-entity relationships for a specific record.
 */
export function useRelationships(
  userId: string | undefined,
  sourceType: SourceType | undefined,
  sourceId: string | undefined
) {
  return useQuery<RelationshipsResponse>({
    queryKey: reflectionKeys.relationships(userId, sourceType!, sourceId!),
    queryFn: () => getRelationships(sourceType!, sourceId!),
    enabled: Boolean(userId) && Boolean(sourceType) && Boolean(sourceId),
    staleTime: 60_000,
  });
}

