/**
 * TanStack Query hook for Backend Health Probe.
 */

import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from '../api/health';
import { HealthResponse } from '../api/types';

export const healthKeys = {
  all: ['health'] as const,
};

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: healthKeys.all,
    queryFn: fetchHealth,
    staleTime: 1000 * 30, // 30 seconds
    refetchInterval: 1000 * 60, // Poll health every 60s
  });
}
