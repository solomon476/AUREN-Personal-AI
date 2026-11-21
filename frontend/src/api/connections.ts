/**
 * Typed API Client for AUREN Trusted Connections and Voluntary Location Sharing.
 */

import { apiClient } from './client';

export interface Connection {
  id: string;
  user_id: string;
  connected_user_id?: string | null;
  invite_code: string;
  display_name: string;
  avatar_initials: string;
  status: 'pending' | 'accepted' | 'declined' | 'revoked';
  location_sharing_active: boolean;
  location_sharing_expires_at?: string | null;
  last_latitude?: number | null;
  last_longitude?: number | null;
  last_location_updated_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectionListResponse {
  items: Connection[];
  total: number;
}

export interface CreateInvitePayload {
  display_name: string;
}

export interface AcceptInvitePayload {
  invite_code: string;
}

export interface LocationSharingTogglePayload {
  enabled: boolean;
  duration_minutes?: number;
  target_connection_ids?: string[];
}

export interface LocationUpdatePayload {
  latitude: number;
  longitude: number;
  accuracy?: number;
}

export const connectionsApi = {
  async list(): Promise<ConnectionListResponse> {
    return apiClient.get<ConnectionListResponse>('/connections');
  },

  async createInvite(displayName: string): Promise<Connection> {
    return apiClient.post<Connection>('/connections/invite', { display_name: displayName });
  },

  async acceptInvite(inviteCode: string): Promise<Connection> {
    return apiClient.post<Connection>('/connections/accept', { invite_code: inviteCode });
  },

  async declineInvite(inviteCode: string): Promise<{ declined: boolean; invite_code: string }> {
    return apiClient.post<{ declined: boolean; invite_code: string }>('/connections/decline', { invite_code: inviteCode });
  },

  async revoke(connectionId: string): Promise<{ revoked: boolean; id: string }> {
    return apiClient.delete<{ revoked: boolean; id: string }>(`/connections/${connectionId}`);
  },

  async toggleLocationSharing(payload: LocationSharingTogglePayload): Promise<{ active: boolean; updated_count: number; expires_at?: string | null }> {
    return apiClient.post<{ active: boolean; updated_count: number; expires_at?: string | null }>('/connections/location-sharing', payload);
  },

  async updateLiveLocation(coords: LocationUpdatePayload): Promise<{ updated: boolean }> {
    return apiClient.post<{ updated: boolean }>('/connections/location-update', coords);
  },
};

