/**
 * Main Application Root.
 * Configures QueryClientProvider, AuthProvider, and TanStack RouterProvider.
 */

import React, { useEffect } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import { queryClient } from './lib/queryClient';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { router } from './router';
import { API_BASE_URL } from './api/client';

export const App: React.FC = () => {
  // Global backend keep-warm ping to eliminate cold-starts across all views
  useEffect(() => {
    const keepWarm = () => {
      fetch(`${API_BASE_URL}/health`).catch(() => {});
    };
    keepWarm();
    const interval = setInterval(keepWarm, 3.5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
};

export default App;
