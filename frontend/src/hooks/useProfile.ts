/**
 * TanStack Query hook for User Profile.
 */

import { useQuery } from '@tanstack/react-query';
import { fetchMyProfile, UserProfileResponse } from '../api/auth';

export const profileKeys = {
  all: ['profile'] as const,
  user: (userId: string | undefined) => [...profileKeys.all, userId ?? 'anonymous'] as const,
};

export function useProfile(userId: string | undefined) {
  return useQuery<UserProfileResponse>({
    queryKey: profileKeys.user(userId),
    queryFn: fetchMyProfile,
    enabled: Boolean(userId),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}
