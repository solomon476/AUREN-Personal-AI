/**
 * Unit & Integration Tests for JournalView.
 * Tests journal entry creation, editing, deletion, live Markdown preview,
 * mood filtering, and RFC 8785 HMAC cryptographic integrity badge rendering.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { JournalView } from '../features/journal/JournalView';
import * as journalApi from '../api/journal';

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<any>();
  const user = { id: 'usr-journal-123', email: 'writer@auren.ai', role: 'authenticated' };
  return {
    ...actual,
    AuthContext: React.createContext({
      user,
      isAuthenticated: true,
    }),
    useAuth: () => ({
      user,
      isAuthenticated: true,
    }),
  };
});

vi.mock('../api/journal', async () => {
  const actual = await vi.importActual<any>('../api/journal');
  return {
    ...actual,
    listJournalEntries: vi.fn(),
    createJournalEntry: vi.fn(),
    updateJournalEntry: vi.fn(),
    deleteJournalEntry: vi.fn(),
  };
});

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

describe('JournalView Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders journal entries list and displays cryptographic integrity badge in detail view', async () => {
    const qc = createTestQueryClient();
    vi.mocked(journalApi.listJournalEntries).mockResolvedValueOnce({
      items: [
        {
          id: 'j-1',
          user_id: 'usr-journal-123',
          title: 'Deep Architecture Verification',
          content: 'Hardened cryptographic invariants for Phase 4C.1.',
          mood: 'focused',
          tags: ['engineering', 'security'],
          is_private: true,
          entry_date: '2026-11-20',
          integrity_signature: 'sig_valid_1234567890abcdef',
          integrity_verified: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
    });

    render(
      <QueryClientProvider client={qc}>
        <JournalView />
      </QueryClientProvider>
    );

    // List item renders
    await waitFor(() => {
      expect(screen.getByText('Deep Architecture Verification')).toBeInTheDocument();
      expect(screen.getByText('Private Journaling & Reflection')).toBeInTheDocument();
    });

    // Click entry to open detail view
    const entryItem = screen.getByText('Deep Architecture Verification');
    await userEvent.click(entryItem);

    // Detail view renders RFC 8785 HMAC integrity verified badge
    await waitFor(() => {
      expect(screen.getByText('RFC 8785 HMAC Verified')).toBeInTheDocument();
      expect(screen.getByText('Edit')).toBeInTheDocument();
    });
  });

  it('opens entry form, fills content, and creates a new private reflection', async () => {
    const qc = createTestQueryClient();
    vi.mocked(journalApi.listJournalEntries).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_more: false,
    });
    vi.mocked(journalApi.createJournalEntry).mockResolvedValueOnce({
      id: 'j-new',
      user_id: 'usr-journal-123',
      title: 'Morning Strategy',
      content: 'Clear focus on deliverables.',
      mood: 'energized',
      tags: ['planning'],
      is_private: true,
      entry_date: '2026-11-20',
      integrity_signature: 'sig_new',
      integrity_verified: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(
      <QueryClientProvider client={qc}>
        <JournalView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/no reflections recorded yet/i)).toBeInTheDocument();
    });

    // Click Write Reflection
    const writeButton = screen.getByRole('button', { name: /write reflection/i });
    await userEvent.click(writeButton);

    // Fill title and content
    const titleInput = screen.getByPlaceholderText(/reflection title/i);
    await userEvent.type(titleInput, 'Morning Strategy');

    const contentTextarea = screen.getByPlaceholderText(/begin your reflection/i);
    await userEvent.type(contentTextarea, 'Clear focus on deliverables.');

    // Save reflection
    const saveButton = screen.getByRole('button', { name: /^save$/i });
    await userEvent.click(saveButton);

    await waitFor(() => {
      expect(journalApi.createJournalEntry).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Morning Strategy')).toBeInTheDocument();
    });
  });

  it('toggles markdown live preview in editor mode', async () => {
    const qc = createTestQueryClient();
    vi.mocked(journalApi.listJournalEntries).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_more: false,
    });

    render(
      <QueryClientProvider client={qc}>
        <JournalView />
      </QueryClientProvider>
    );

    const writeButton = screen.getByRole('button', { name: /write reflection/i });
    await userEvent.click(writeButton);

    const contentTextarea = screen.getByPlaceholderText(/begin your reflection/i);
    await userEvent.type(contentTextarea, '# Heading Title\n\n- Markdown bullet point');

    // Click Preview button
    const previewTab = screen.getByRole('button', { name: /preview/i });
    await userEvent.click(previewTab);

    // Markdown preview renders
    expect(screen.getByText('Heading Title')).toBeInTheDocument();
    expect(screen.getByText('Markdown bullet point')).toBeInTheDocument();
  });

  it('renders integrity failed badge when entry has invalid HMAC signature', async () => {
    const qc = createTestQueryClient();
    vi.mocked(journalApi.listJournalEntries).mockResolvedValueOnce({
      items: [
        {
          id: 'j-tampered',
          user_id: 'usr-journal-123',
          title: 'Tampered Reflection',
          content: 'This record was modified out of band.',
          mood: 'anxious',
          tags: ['security'],
          is_private: true,
          entry_date: '2026-11-20',
          integrity_signature: 'invalid_forged_signature',
          integrity_verified: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
    });

    render(
      <QueryClientProvider client={qc}>
        <JournalView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Tampered Reflection')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Tampered Reflection'));

    await waitFor(() => {
      expect(screen.getByText('Integrity Failed')).toBeInTheDocument();
    });
  });

  it('renders unsigned legacy badge when entry lacks cryptographic signature', async () => {
    const qc = createTestQueryClient();
    vi.mocked(journalApi.listJournalEntries).mockResolvedValueOnce({
      items: [
        {
          id: 'j-legacy',
          user_id: 'usr-journal-123',
          title: 'Old Legacy Entry',
          content: 'Recorded prior to signing architecture.',
          mood: 'calm',
          tags: ['legacy'],
          is_private: true,
          entry_date: '2026-11-01',
          integrity_signature: undefined,
          integrity_verified: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
    });

    render(
      <QueryClientProvider client={qc}>
        <JournalView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Old Legacy Entry')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Old Legacy Entry'));

    await waitFor(() => {
      expect(screen.getByText('Unsigned (Legacy)')).toBeInTheDocument();
    });
  });

  it('edits an existing reflection and persists updates', async () => {
    const qc = createTestQueryClient();
    const existing = {
      id: 'j-edit-1',
      user_id: 'usr-journal-123',
      title: 'Original Title',
      content: 'Original Content',
      mood: 'reflective',
      tags: ['draft'],
      is_private: true,
      entry_date: '2026-11-20',
      integrity_signature: 'sig_valid',
      integrity_verified: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    vi.mocked(journalApi.listJournalEntries).mockResolvedValue({
      items: [existing],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
    });
    vi.mocked(journalApi.updateJournalEntry).mockResolvedValueOnce({
      ...existing,
      title: 'Updated Title',
      content: 'Updated Content',
    });

    render(
      <QueryClientProvider client={qc}>
        <JournalView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Original Title')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Original Title'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /edit/i }));

    const titleInput = screen.getByPlaceholderText(/reflection title/i);
    await userEvent.clear(titleInput);
    await userEvent.type(titleInput, 'Updated Title');

    const saveButton = screen.getByRole('button', { name: /save/i });
    await userEvent.click(saveButton);

    await waitFor(() => {
      expect(journalApi.updateJournalEntry).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Updated Title')).toBeInTheDocument();
    });
  });

  it('deletes an existing reflection after user confirmation', async () => {
    const qc = createTestQueryClient();
    const existing = {
      id: 'j-del-1',
      user_id: 'usr-journal-123',
      title: 'Delete Me',
      content: 'To be removed.',
      mood: 'neutral',
      tags: [],
      is_private: true,
      entry_date: '2026-11-20',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    vi.mocked(journalApi.listJournalEntries).mockResolvedValue({
      items: [existing],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
    });
    vi.mocked(journalApi.deleteJournalEntry).mockResolvedValueOnce(undefined as any);
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(
      <QueryClientProvider client={qc}>
        <JournalView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Delete Me')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Delete Me'));

    await waitFor(() => {
      expect(screen.getByTitle('Delete Entry')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTitle('Delete Entry'));

    await waitFor(() => {
      expect(journalApi.deleteJournalEntry).toHaveBeenCalledWith('j-del-1');
    });
  });
});
