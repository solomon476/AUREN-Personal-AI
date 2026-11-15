/**
 * Shared API response types
 */

export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  environment: string;
  timestamp: string;
}

export interface ApiErrorResponse {
  detail: string;
}

