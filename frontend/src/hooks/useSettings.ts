/**
 * TanStack Query hooks for User Profile, Preferences, and Data Export.
 */

import { useContext } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AuthContext } from '../context/AuthContext';
import {
  exportUserData,
  getUserProfile,
  updateUserProfile,
  UserProfile,
  UserProfileUpdateInput,
} from '../api/settings';

export function useCurrentUserId(explicitUserId?: string): string {
  const auth = useContext(AuthContext);
  return explicitUserId ?? auth?.user?.id ?? 'anonymous';
}

export const SETTINGS_KEYS = {
  profile: (userId?: string) => ['settings', 'profile', userId ?? 'anonymous'] as const,
};

export function useUserProfile(userId?: string) {
  const currentUserId = useCurrentUserId(userId);
  const isAuthenticated = currentUserId !== 'anonymous';

  return useQuery({
    queryKey: SETTINGS_KEYS.profile(currentUserId),
    queryFn: async (): Promise<UserProfile> => {
      return getUserProfile();
    },
    enabled: isAuthenticated,
    staleTime: 1000 * 60,
  });
}

export function useUpdateUserProfile(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);

  return useMutation({
    mutationFn: (payload: UserProfileUpdateInput) => updateUserProfile(payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(SETTINGS_KEYS.profile(currentUserId), updated);
    },
  });
}

export function useExportUserData() {
  return useMutation({
    mutationFn: () => exportUserData(),
  });
}
