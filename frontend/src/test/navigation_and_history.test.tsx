/**
 * Test Suite 2: Navigation, Browser History, and Route Handling.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderRouter } from './test-utils';

vi.mock('../api/chat', () => ({
  listConversations: vi.fn().mockResolvedValue([]),
  getConversationMessages: vi.fn().mockResolvedValue([]),
  createConversation: vi.fn(),
  streamChat: vi.fn(),
}));

vi.mock('../api/health', () => ({
  fetchHealth: vi.fn().mockResolvedValue({
    status: 'healthy',
    app_name: 'auren-backend',
    version: '0.1.0',
    environment: 'test',
    timestamp: '2026-11-16T00:00:00Z',
  }),
}));

describe('Navigation and Browser History', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('navigates from /chat to /system when clicking System & Database', async () => {
    const user = userEvent.setup();
    const { history } = await renderRouter('/chat');

    const systemNavLink = screen.getByRole('link', { name: /system & database/i });
    await user.click(systemNavLink);

    await waitFor(() => {
      expect(history.location.pathname).toBe('/system');
      expect(screen.getByText('PostgreSQL Schemas & RLS Policies')).toBeInTheDocument();
      expect(screen.getByText('FastAPI Backend & Streaming Health')).toBeInTheDocument();
    });
  });

  it('navigates to roadmap sections and renders honest placeholder details', async () => {
    const user = userEvent.setup();
    const { history } = await renderRouter('/chat');

    // Click Long-term Memory
    const memoryLink = screen.getByRole('link', { name: /long-term memory/i });
    await user.click(memoryLink);

    await waitFor(() => {
      expect(history.location.pathname).toBe('/memories');
      expect(screen.getByText('Long-term Memory & Epistemic Verification')).toBeInTheDocument();
      expect(screen.getByText(/Phase 3B Backend Operational/i)).toBeInTheDocument();
      expect(screen.getByText(/Interactive Memory Explorer & Category Filter/i)).toBeInTheDocument();
    });
  });

  it('handles browser back and forward navigation correctly', async () => {
    const user = userEvent.setup();
    const { history } = await renderRouter('/chat');

    // 1. Navigate to /system
    const systemLink = screen.getByRole('link', { name: /system & database/i });
    await user.click(systemLink);
    await waitFor(() => expect(history.location.pathname).toBe('/system'));

    // 2. Navigate to /tasks
    const tasksLink = screen.getByRole('link', { name: /tasks & timetable/i });
    await user.click(tasksLink);
    await waitFor(() => expect(history.location.pathname).toBe('/tasks'));

    // 3. Browser Back -> should return to /system
    history.back();
    await waitFor(() => {
      expect(history.location.pathname).toBe('/system');
      expect(screen.getByText('PostgreSQL Schemas & RLS Policies')).toBeInTheDocument();
    });

    // 4. Browser Forward -> should return to /tasks
    history.forward();
    await waitFor(() => {
      expect(history.location.pathname).toBe('/tasks');
      expect(screen.getByText('Tasks & Timetable')).toBeInTheDocument();
    });
  });

  it('renders NotFound component on invalid route', async () => {
    await renderRouter('/non-existent-endpoint-404');

    await waitFor(() => {
      expect(screen.getByText('Page Not Found')).toBeInTheDocument();
      expect(screen.getByText(/The requested destination does not exist/i)).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /return to ai chat/i })).toBeInTheDocument();
    });
  });
});
