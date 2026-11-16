/**
 * Main Application Root.
 * Configures QueryClientProvider, AuthProvider, and TanStack RouterProvider.
 */

import React from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import { queryClient } from './lib/queryClient';
import { AuthProvider } from './context/AuthContext';
import { router } from './router';

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
};

export default App;
