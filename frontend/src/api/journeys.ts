/**
 * Typed API Client for AUREN GPS Journeys and Offline Sync.
 */

import { apiClient } from './client';

export interface GPSPoint {
  lat: number;
  lng: number;
  altitude?: number | null;
  accuracy: number;
  speed?: number | null;
  heading?: number | null;
  timestamp: string;
}

export interface Journey {
  id: string;
  user_id: string;
  title: string;
  status: 'recording' | 'paused' | 'completed' | 'cancelled';
  distance_meters: number;
  duration_seconds: number;
  avg_speed_kmh?: number | null;
  is_offline_recorded: boolean;
  is_team_assignment: boolean;
  assignment_site?: string | null;
  assignment_purpose?: string | null;
  assignment_notes?: string | null;
  check_in_time?: string | null;
  check_in_coords?: string | null;
  points: GPSPoint[];
  idempotency_key?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface JourneyCreatePayload {
  id?: string;
  title?: string;
  status?: string;
  distance_meters?: number;
  duration_seconds?: number;
  avg_speed_kmh?: number | null;
  is_offline_recorded?: boolean;
  is_team_assignment?: boolean;
  assignment_site?: string | null;
  assignment_purpose?: string | null;
  assignment_notes?: string | null;
  check_in_time?: string | null;
  check_in_coords?: string | null;
  points?: GPSPoint[];
  idempotency_key?: string | null;
  completed_at?: string | null;
}

export interface JourneyListResponse {
  items: Journey[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface JourneySyncBatchPayload {
  journeys: JourneyCreatePayload[];
}

export interface JourneySyncBatchResponse {
  synced_count: number;
  skipped_count: number;
  journeys: Journey[];
}

export const journeysApi = {
  async list(page = 1, pageSize = 30): Promise<JourneyListResponse> {
    return apiClient.get<JourneyListResponse>(`/journeys?page=${page}&page_size=${pageSize}`);
  },

  async get(id: string): Promise<Journey> {
    return apiClient.get<Journey>(`/journeys/${id}`);
  },

  async create(payload: JourneyCreatePayload): Promise<Journey> {
    return apiClient.post<Journey>('/journeys', payload);
  },

  async syncBatch(payload: JourneySyncBatchPayload): Promise<JourneySyncBatchResponse> {
    return apiClient.post<JourneySyncBatchResponse>('/journeys/sync-batch', payload);
  },

  async delete(id: string): Promise<{ deleted: boolean; id: string }> {
    return apiClient.delete<{ deleted: boolean; id: string }>(`/journeys/${id}`);
  },
};

