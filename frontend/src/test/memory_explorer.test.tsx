/**
 * Test Suite: Memory Explorer & Epistemic Verification.
 * Verifies rendering, filtering, search, modal detail inspection,
 * epistemic confirmation, and lineage-preserving corrections.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryView } from '../features/memory/MemoryView';
import { MemoryDetailModal } from '../components/memory/MemoryDetailModal';
import { Memory } from '../api/memories';
import { createWrapper } from './test-utils';
import * as memoryApi from '../api/memories';

vi.mock('../api/memories', () => ({
  listMemories: vi.fn(),
  getMemory: vi.fn(),
  createMemory: vi.fn(),
  confirmMemory: vi.fn(),
  rejectMemory: vi.fn(),
  correctMemory: vi.fn(),
  archiveMemory: vi.fn(),
  restoreMemory: vi.fn(),
  outdateMemory: vi.fn(),
  getMessageContext: vi.fn(),
}));

const mockMemories: Memory[] = [
  {
    id: 'mem-1',
    content: 'User prefers dark mode UI and concise code examples.',
    memory_type: 'preference',
    category: 'technical',
    importance: 4,
    confidence: 0.95,
    confirmation_status: 'confirmed',
    lifecycle_status: 'active',
    origin: 'user_direct_input',
    access_count: 5,
    created_at: '2026-11-16T10:00:00Z',
    updated_at: '2026-11-16T10:00:00Z',
  },
  {
    id: 'mem-2',
    content: 'User is working on the AUREN AI assistant project.',
    memory_type: 'project',
    category: 'work',
    importance: 5,
    confidence: 0.8,
    confirmation_status: 'unconfirmed',
    lifecycle_status: 'active',
    origin: 'chat_inferred',
    access_count: 2,
    created_at: '2026-11-16T11:00:00Z',
    updated_at: '2026-11-16T11:00:00Z',
  },
];

describe('Memory Explorer: View & Filters', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders header, search bar, and memory cards', async () => {
    vi.mocked(memoryApi.listMemories).mockResolvedValue({
      items: mockMemories,
      total: 2,
      page: 1,
      page_size: 12,
      has_more: false,
    });

    render(<MemoryView />, { wrapper: createWrapper() });

    expect(screen.getByText('Long-term Memory Explorer')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search memory content/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/User prefers dark mode UI/i)).toBeInTheDocument();
      expect(screen.getByText(/User is working on the AUREN AI assistant/i)).toBeInTheDocument();
    });

    // Check status badges
    expect(screen.getAllByText('Confirmed').length).toBeGreaterThan(0);
    expect(screen.getByText('Inference')).toBeInTheDocument();
  });

  it('displays empty state when no memories exist', async () => {
    vi.mocked(memoryApi.listMemories).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 12,
      has_more: false,
    });

    render(<MemoryView />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('No memories found')).toBeInTheDocument();
    });
  });

  it('triggers search on input change', async () => {
    const user = userEvent.setup();
    vi.mocked(memoryApi.listMemories).mockResolvedValue({
      items: mockMemories,
      total: 2,
      page: 1,
      page_size: 12,
      has_more: false,
    });

    render(<MemoryView />, { wrapper: createWrapper() });

    const searchInput = screen.getByPlaceholderText(/search memory content/i);
    await user.type(searchInput, 'dark mode');

    await waitFor(() => {
      expect(memoryApi.listMemories).toHaveBeenCalledWith(
        expect.objectContaining({ query: 'dark mode' })
      );
    });
  });

  it('opens and submits new memory modal', async () => {
    const user = userEvent.setup();
    vi.mocked(memoryApi.listMemories).mockResolvedValue({
      items: mockMemories,
      total: 2,
      page: 1,
      page_size: 12,
      has_more: false,
    });
    vi.mocked(memoryApi.createMemory).mockResolvedValue({
      id: 'mem-3',
      content: 'New manual memory entry',
      memory_type: 'fact',
      category: 'general',
      importance: 3,
      confirmation_status: 'confirmed',
      lifecycle_status: 'active',
      origin: 'user_direct_input',
      access_count: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(<MemoryView />, { wrapper: createWrapper() });

    const addButton = screen.getByRole('button', { name: /add memory/i });
    await user.click(addButton);

    expect(screen.getByRole('heading', { name: /add confirmed memory/i })).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/prefers technical documentation/i);
    await user.type(textarea, 'New manual memory entry');

    const saveButton = screen.getByRole('button', { name: /save confirmed memory/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(memoryApi.createMemory).toHaveBeenCalledWith({
        content: 'New manual memory entry',
        memory_type: 'fact',
        category: 'general',
        importance: 3,
      });
    });
  });
});

describe('Memory Detail Modal & Epistemic Verification', () => {
  it('renders complete metadata, provenance, and epistemic explanation', () => {
    const memory = mockMemories[1]; // unconfirmed inference
    const onClose = vi.fn();

    render(
      <MemoryDetailModal
        memory={memory}
        isOpen={true}
        onClose={onClose}
      />
    );

    expect(screen.getByRole('heading', { name: /memory details/i })).toBeInTheDocument();
    expect(screen.getByText(/Unconfirmed Inference/i)).toBeInTheDocument();
    expect(screen.getByText(/Not yet confirmed by you/i)).toBeInTheDocument();
    expect(screen.getByText(/chat_inferred/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /confirm inference/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject inference/i })).toBeInTheDocument();
  });

  it('triggers confirmation on unconfirmed memory', async () => {
    const user = userEvent.setup();
    const memory = mockMemories[1];
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(
      <MemoryDetailModal
        memory={memory}
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    const confirmButton = screen.getByRole('button', { name: /confirm inference/i });
    await user.click(confirmButton);

    expect(onConfirm).toHaveBeenCalledWith('mem-2');
  });

  it('opens inline correction form and submits lineage-preserving correction', async () => {
    const user = userEvent.setup();
    const memory = mockMemories[0];
    const onCorrect = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(
      <MemoryDetailModal
        memory={memory}
        isOpen={true}
        onClose={onClose}
        onCorrect={onCorrect}
      />
    );

    // Click "Correct Memory"
    const correctButton = screen.getByRole('button', { name: /correct memory/i });
    await user.click(correctButton);

    // Form appears
    expect(screen.getByText(/Preserves Historical Lineage/i)).toBeInTheDocument();
    const textarea = screen.getByDisplayValue(memory.content);

    await user.clear(textarea);
    await user.type(textarea, 'Updated preferred programming workflow');

    const saveButton = screen.getByRole('button', { name: /save lineage-preserving correction/i });
    await user.click(saveButton);

    expect(onCorrect).toHaveBeenCalledWith('mem-1', expect.objectContaining({
      content: 'Updated preferred programming workflow',
      memory_type: 'preference',
      category: 'technical',
      importance: 4,
    }));
  });
});
