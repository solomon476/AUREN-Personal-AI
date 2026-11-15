/**
 * Health check API service.
 */

import { apiClient } from './client';
import { HealthResponse } from './types';

export async function fetchHealth(): Promise<HealthResponse> {
  return apiClient.get<HealthResponse>('/health');
}

