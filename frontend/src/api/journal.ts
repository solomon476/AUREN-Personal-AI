/**
 * Typed API Client for AUREN Private Journal.
 * All operations are strictly authenticated and isolated by user ID.
 */

import { apiClient } from './client';

export interface JournalEntry {
  id: string;
  user_id: string;
  title: string | null;
  content: string;
  mood: string | null;
  tags: string[];
  is_private: boolean;
  entry_date: string;
  integrity_signature?: string | null;
  integrity_verified?: boolean | null;
  created_at: string;
  updated_at: string;
}

export interface JournalEntryCreate {
  title?: string;
  content: string;
  mood?: string;
  tags?: string[];
  is_private?: boolean;
  entry_date?: string;
}

export interface JournalEntryUpdate {
  title?: string;
  content?: string;
  mood?: string;
  tags?: string[];
  is_private?: boolean;
  entry_date?: string;
}

export interface JournalEntryListResponse {
  items: JournalEntry[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface JournalListParams {
  page?: number;
  page_size?: number;
  start_date?: string;
  end_date?: string;
  mood?: string;
  query?: string;
}

export async function listJournalEntries(params?: JournalListParams): Promise<JournalEntryListResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set('page', String(params.page));
  if (params?.page_size) query.set('page_size', String(params.page_size));
  if (params?.start_date) query.set('start_date', params.start_date);
  if (params?.end_date) query.set('end_date', params.end_date);
  if (params?.mood) query.set('mood', params.mood);
  if (params?.query) query.set('query', params.query);

  const qs = query.toString();
  return apiClient.get<JournalEntryListResponse>(`/journal${qs ? `?${qs}` : ''}`);
}

export async function getJournalEntry(entryId: string): Promise<JournalEntry> {
  return apiClient.get<JournalEntry>(`/journal/${entryId}`);
}

export async function createJournalEntry(payload: JournalEntryCreate): Promise<JournalEntry> {
  return apiClient.post<JournalEntry>('/journal', payload);
}

export async function updateJournalEntry(entryId: string, payload: JournalEntryUpdate): Promise<JournalEntry> {
  return apiClient.patch<JournalEntry>(`/journal/${entryId}`, payload);
}

export async function deleteJournalEntry(entryId: string): Promise<void> {
  return apiClient.delete<void>(`/journal/${entryId}`);
}
