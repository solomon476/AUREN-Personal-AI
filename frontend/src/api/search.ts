/**
 * Phase 3C.5: Omnisearch & Reflection API client.
 *
 * All requests are authenticated via the Supabase session token and
 * scoped exclusively to the authenticated user. No cross-tenant data
 * is accessible through these endpoints.
 */

import { apiClient } from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SourceType =
  | 'conversation'
  | 'message'
  | 'memory'
  | 'task'
  | 'project'
  | 'goal';

export type RelationshipType =
  | 'related'
  | 'supports'
  | 'contradicts'
  | 'supersedes'
  | 'derived_from'
  | 'referenced_in';

export interface SearchResultItem {
  source_type: SourceType;
  id: string;
  title: string;
  snippet: string;
  created_at: string;
  updated_at: string | null;
  score: number;
  provenance: string;
  navigation_path: string;
  metadata: Record<string, unknown>;
}

export interface OmnisearchResponse {
  query: string;
  sources_searched: SourceType[];
  results: SearchResultItem[];
  total_count: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface OmnisearchParams {
  q: string;
  sources?: SourceType[];
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export interface ContradictionItem {
  memory_a_id: string;
  memory_a_content: string;
  memory_a_status: string;
  memory_b_id: string;
  memory_b_content: string;
  memory_b_status: string;
  contradiction_type: string;
  explanation: string;
  confidence: number;
  suggested_action: string;
}

export interface StalenessItem {
  source_type: SourceType;
  id: string;
  title: string;
  reason: string;
  last_updated: string | null;
  navigation_path: string;
  staleness_score: number;
}

export interface ReflectionInsightsResponse {
  contradiction_count: number;
  staleness_count: number;
  inferred_link_count: number;
  contradictions: ContradictionItem[];
  staleness_items: StalenessItem[];
  generated_at: string;
}

export interface RelatedRecord {
  source_type: SourceType;
  id: string;
  title: string;
  relationship_type: RelationshipType;
  relationship_source: string;
  confidence: number;
  navigation_path: string;
}

export interface RelationshipsResponse {
  source_type: SourceType;
  source_id: string;
  relationships: RelatedRecord[];
  total_count: number;
}

// ---------------------------------------------------------------------------
// Omnisearch API
// ---------------------------------------------------------------------------

export async function omnisearch(params: OmnisearchParams): Promise<OmnisearchResponse> {
  const query = new URLSearchParams();
  query.set('q', params.q);
  if (params.sources && params.sources.length > 0) {
    params.sources.forEach((s) => query.append('sources', s));
  }
  if (params.date_from) query.set('date_from', params.date_from);
  if (params.date_to) query.set('date_to', params.date_to);
  if (params.page !== undefined) query.set('page', String(params.page));
  if (params.page_size !== undefined) query.set('page_size', String(params.page_size));

  return apiClient.get<OmnisearchResponse>(`/search?${query.toString()}`);
}

// ---------------------------------------------------------------------------
// Reflection API
// ---------------------------------------------------------------------------

export async function getReflectionInsights(): Promise<ReflectionInsightsResponse> {
  return apiClient.get<ReflectionInsightsResponse>('/reflection/insights');
}

export async function getContradictions(): Promise<{ contradictions: ContradictionItem[]; count: number }> {
  return apiClient.get<{ contradictions: ContradictionItem[]; count: number }>(
    '/reflection/contradictions'
  );
}

export async function getStaleness(): Promise<{ items: StalenessItem[]; count: number }> {
  return apiClient.get<{ items: StalenessItem[]; count: number }>(
    '/reflection/staleness'
  );
}

export async function getRelationships(
  sourceType: SourceType,
  sourceId: string
): Promise<RelationshipsResponse> {
  return apiClient.get<RelationshipsResponse>(
    `/reflection/relationships?source_type=${sourceType}&source_id=${sourceId}`
  );
}
