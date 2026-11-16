/**
 * Memory Management & Epistemic Verification API client.
 * Provides typed operations for memory exploration, lifecycle transitions,
 * historical lineage corrections, and context provenance inspection.
 */

import { apiClient } from './client';

export type MemoryType = 'fact' | 'preference' | 'goal' | 'project' | 'context' | 'observation';
export type MemoryCategory = 'personal' | 'work' | 'technical' | 'health_lifestyle' | 'financial' | 'general';
export type MemoryLifecycleStatus = 'active' | 'superseded' | 'expired' | 'archived' | 'rejected' | 'forgotten';
export type MemoryConfirmationStatus = 'confirmed' | 'unconfirmed' | 'rejected' | 'system_asserted';
export type MemoryOrigin =
  | 'explicit_user_statement'
  | 'inferred_dialogue'
  | 'user_direct_input'
  | 'user_direct_edit'
  | 'chat_inferred'
  | 'journal_inferred'
  | 'system_asserted'
  | 'legacy_import';

export interface Memory {
  id: string;
  content: string;
  memory_type: MemoryType;
  category: MemoryCategory;
  importance: number;
  confidence?: number | null;
  confirmation_status: MemoryConfirmationStatus;
  lifecycle_status: MemoryLifecycleStatus;
  origin: MemoryOrigin;
  source_message_id?: string | null;
  source_conversation_id?: string | null;
  superseded_by_id?: string | null;
  previous_version_id?: string | null;
  root_memory_id?: string | null;
  access_count: number;
  last_accessed_at?: string | null;
  last_confirmed_at?: string | null;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}

export interface MemoryListResponse {
  items: Memory[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface MemoryFilterParams {
  query?: string;
  memory_type?: string;
  category?: string;
  confirmation_status?: string;
  lifecycle_status?: string;
  page?: number;
  page_size?: number;
}

export interface CreateMemoryPayload {
  content: string;
  memory_type?: MemoryType;
  category?: MemoryCategory;
  importance?: number;
}

export interface CorrectMemoryPayload {
  content: string;
  memory_type?: MemoryType;
  category?: MemoryCategory;
  importance?: number;
}

export interface MemoryContextItem {
  id: string;
  content: string;
  memory_type: string;
  category: string;
  confirmation_status: string;
  importance: number;
  score: number;
}

export interface MessageContextResponse {
  message_id: string;
  conversation_id: string;
  model?: string | null;
  retrieved_memories: MemoryContextItem[];
  memory_count: number;
}

export async function listMemories(params: MemoryFilterParams = {}): Promise<MemoryListResponse> {
  const queryParts: string[] = [];
  if (params.query) queryParts.push(`query=${encodeURIComponent(params.query)}`);
  if (params.memory_type) queryParts.push(`memory_type=${encodeURIComponent(params.memory_type)}`);
  if (params.category) queryParts.push(`category=${encodeURIComponent(params.category)}`);
  if (params.confirmation_status) queryParts.push(`confirmation_status=${encodeURIComponent(params.confirmation_status)}`);
  if (params.lifecycle_status) queryParts.push(`lifecycle_status=${encodeURIComponent(params.lifecycle_status)}`);
  if (params.page) queryParts.push(`page=${params.page}`);
  if (params.page_size) queryParts.push(`page_size=${params.page_size}`);

  const qs = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
  return apiClient.get<MemoryListResponse>(`/memories${qs}`);
}

export async function getMemory(memoryId: string): Promise<Memory> {
  return apiClient.get<Memory>(`/memories/${memoryId}`);
}

export async function createMemory(payload: CreateMemoryPayload): Promise<Memory> {
  return apiClient.post<Memory>('/memories', payload);
}

export async function confirmMemory(memoryId: string): Promise<Memory> {
  return apiClient.post<Memory>(`/memories/${memoryId}/confirm`);
}

export async function rejectMemory(memoryId: string): Promise<Memory> {
  return apiClient.post<Memory>(`/memories/${memoryId}/reject`);
}

export async function correctMemory(memoryId: string, payload: CorrectMemoryPayload): Promise<Memory> {
  return apiClient.post<Memory>(`/memories/${memoryId}/correct`, payload);
}

export async function archiveMemory(memoryId: string): Promise<Memory> {
  return apiClient.post<Memory>(`/memories/${memoryId}/archive`);
}

export async function restoreMemory(memoryId: string): Promise<Memory> {
  return apiClient.post<Memory>(`/memories/${memoryId}/restore`);
}

export async function outdateMemory(memoryId: string): Promise<Memory> {
  return apiClient.post<Memory>(`/memories/${memoryId}/outdated`);
}

export async function getMessageContext(conversationId: string, messageId: string): Promise<MessageContextResponse> {
  return apiClient.get<MessageContextResponse>(`/chat/conversations/${conversationId}/messages/${messageId}/context`);
}
