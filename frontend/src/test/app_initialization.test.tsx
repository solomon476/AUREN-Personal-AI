/**
 * Test Suite 1: Application Initialization & Root Route.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderRouter } from './test-utils';

// Mock chat API
vi.mock('../api/chat', () => ({
  listConversations: vi.fn().mockResolvedValue([
    {
      id: 'conv-init-1',
      title: 'Initial Test Dialogue',
      created_at: '2026-11-16T00:00:00Z',
      updated_at: '2026-11-16T00:00:00Z',
      message_count: 3,
    },
  ]),
  getConversationMessages: vi.fn().mockResolvedValue([]),
  createConversation: vi.fn(),
  streamChat: vi.fn(),
}));

// Mock health API
vi.mock('../api/health', () => ({
  fetchHealth: vi.fn().mockResolvedValue({
    status: 'healthy',
    app_name: 'auren-backend',
    version: '0.1.0',
    environment: 'test',
    timestamp: '2026-11-16T00:00:00Z',
  }),
}));

describe('Application Initialization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders application shell with branding and navigation', async () => {
    await renderRouter('/chat');

    await waitFor(() => {
      // Verify brand heading
      expect(screen.getAllByText('AUREN').length).toBeGreaterThan(0);
      expect(screen.getByText('Phase 3C')).toBeInTheDocument();

      // Verify primary navigation items
      expect(screen.getByText('AI Assistant')).toBeInTheDocument();
      expect(screen.getByText('System & Database')).toBeInTheDocument();

      // Verify roadmap sections
      expect(screen.getByText('Long-term Memory')).toBeInTheDocument();
      expect(screen.getByText('Tasks & Timetable')).toBeInTheDocument();
      expect(screen.getByText('Projects')).toBeInTheDocument();
      expect(screen.getByText('Goals & Milestones')).toBeInTheDocument();
      expect(screen.getByText('Private Journal')).toBeInTheDocument();
    });
  });

  it('redirects root route (/) to (/chat)', async () => {
    const { history } = await renderRouter('/');

    await waitFor(() => {
      expect(history.location.pathname).toBe('/chat');
    });
  });
});
