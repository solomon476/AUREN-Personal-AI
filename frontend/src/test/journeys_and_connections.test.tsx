/**
 * Test Suite for GPS Journeys, Offline Recording, and Trusted Connections.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import {
  calculateHaversineDistance,
  shouldAcceptGPSPoint,
} from '../lib/offlineJourneys';
import { JourneysView } from '../features/journeys/JourneysView';
import { ConnectionsView } from '../features/connections/ConnectionsView';
import { renderWithProviders } from './test-utils';
import { connectionsApi } from '../api/connections';

// Mock API clients
vi.mock('../api/journeys', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/journeys')>();
  return {
    ...actual,
    journeysApi: {
      list: vi.fn().mockResolvedValue({
        items: [
          {
            id: 'mock-jrn-1',
            user_id: 'user-123',
            title: 'Sector 4 Perimeter Route',
            status: 'completed',
            distance_meters: 2450,
            duration_seconds: 1200,
            avg_speed_kmh: 7.3,
            is_offline_recorded: false,
            is_team_assignment: true,
            assignment_site: 'Sector 4 Solar Array',
            assignment_purpose: 'Routine Audit',
            points: [
              { lat: 37.7749, lng: -122.4194, accuracy: 4, timestamp: '2026-11-21T10:00:00Z' },
              { lat: 37.7755, lng: -122.4201, accuracy: 5, timestamp: '2026-11-21T10:10:00Z' },
            ],
            created_at: '2026-11-21T10:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 30,
        has_more: false,
      }),
      create: vi.fn().mockResolvedValue({ id: 'new-jrn', title: 'Test' }),
      syncBatch: vi.fn().mockResolvedValue({ synced_count: 1, skipped_count: 0, journeys: [] }),
      delete: vi.fn().mockResolvedValue({ deleted: true, id: 'mock-jrn-1' }),
    },
  };
});

vi.mock('../api/connections', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/connections')>();
  return {
    ...actual,
    connectionsApi: {
      list: vi.fn().mockResolvedValue({
        items: [
          {
            id: 'conn-1',
            user_id: 'user-123',
            invite_code: 'aur_f7d82a1b',
            display_name: 'Elena Rostova',
            avatar_initials: 'ER',
            status: 'accepted',
            location_sharing_active: true,
            location_sharing_expires_at: '2026-11-21T11:00:00Z',
            last_latitude: 37.7833,
            last_longitude: -122.4167,
            last_location_updated_at: '2026-11-21T10:15:00Z',
            created_at: '2026-11-21T09:00:00Z',
            updated_at: '2026-11-21T10:15:00Z',
          },
        ],
        total: 1,
      }),
      createInvite: vi.fn().mockResolvedValue({
        id: 'conn-2',
        user_id: 'user-123',
        invite_code: 'aur_1234abcd',
        display_name: 'Marcus Vance',
        avatar_initials: 'MV',
        status: 'pending',
        location_sharing_active: false,
        created_at: '2026-11-21T10:00:00Z',
        updated_at: '2026-11-21T10:00:00Z',
      }),
      acceptInvite: vi.fn().mockResolvedValue({ id: 'conn-3', status: 'accepted' }),
      revoke: vi.fn().mockResolvedValue({ revoked: true, id: 'conn-1' }),
      toggleLocationSharing: vi.fn().mockResolvedValue({ active: true, updated_count: 1, expires_at: '2026-11-21T11:00:00Z' }),
      updateLiveLocation: vi.fn().mockResolvedValue({ updated: true }),
    },
  };
});

describe('AUREN GPS Calculations & Noise Filtering', () => {
  it('accurately computes Haversine distance between two coordinates', () => {
    // San Francisco (37.7749, -122.4194) to Oakland (37.8044, -122.2711) ~ 13.5km
    const dist = calculateHaversineDistance(37.7749, -122.4194, 37.8044, -122.2711);
    expect(dist).toBeGreaterThan(12000);
    expect(dist).toBeLessThan(15000);
  });

  it('rejects GPS fixes with horizontal accuracy worse than 35m', () => {
    const point = {
      lat: 37.7749,
      lng: -122.4194,
      accuracy: 50, // Poor accuracy
      timestamp: new Date().toISOString(),
    };
    expect(shouldAcceptGPSPoint(point, null)).toBe(false);
  });

  it('filters out stationary drift (< 3m movement with zero speed)', () => {
    const p1 = {
      lat: 37.7749,
      lng: -122.4194,
      accuracy: 5,
      timestamp: '2026-11-21T10:00:00Z',
    };
    // Coordinate with ~1 meter jitter
    const p2 = {
      lat: 37.774905,
      lng: -122.419405,
      accuracy: 5,
      speed: 0.1,
      timestamp: '2026-11-21T10:00:05Z',
    };
    expect(shouldAcceptGPSPoint(p2, p1)).toBe(false);
  });

  it('accepts legitimate movement points', () => {
    const p1 = {
      lat: 37.7749,
      lng: -122.4194,
      accuracy: 4,
      timestamp: '2026-11-21T10:00:00Z',
    };
    // Coordinate ~20 meters away at 1.5 m/s walking speed
    const p2 = {
      lat: 37.7751,
      lng: -122.4194,
      accuracy: 4,
      speed: 1.5,
      timestamp: '2026-11-21T10:00:10Z',
    };
    expect(shouldAcceptGPSPoint(p2, p1)).toBe(true);
  });
});

describe('GPS Journeys View & Recorder', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders GPS Journeys header and switcher tabs', () => {
    renderWithProviders(<JourneysView />);

    expect(screen.getByRole('heading', { level: 1, name: /gps journeys/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /active recorder/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /journey history/i })).toBeInTheDocument();
  });

  it('allows starting a journey and toggling team field assignment', async () => {
    renderWithProviders(<JourneysView />);

    // Starts in Active Recorder tab
    const startBtn = screen.getByRole('button', { name: /start journey/i });
    expect(startBtn).toBeInTheDocument();

    // Toggle team assignment checkbox
    const teamCheckbox = screen.getByRole('checkbox', { name: /tag as field assignment/i });
    fireEvent.click(teamCheckbox);

    // Verify fields appear
    expect(screen.getByPlaceholderText(/sector 4 solar array/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/routine sensor calibration/i)).toBeInTheDocument();
  });

  it('switches to Journey History tab and renders recorded journeys', async () => {
    renderWithProviders(<JourneysView />);

    const historyTab = screen.getByRole('button', { name: /journey history/i });
    fireEvent.click(historyTab);

    await waitFor(() => {
      expect(screen.getByText(/sector 4 perimeter route/i)).toBeInTheDocument();
      expect(screen.getByText(/2.45 km/i)).toBeInTheDocument();
      expect(screen.getByText(/synced/i)).toBeInTheDocument();
    });
  });
});

describe('Trusted Connections & Voluntary Location Sharing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Connections view, location sharing status, and accepted contacts', async () => {
    renderWithProviders(<ConnectionsView />);

    expect(screen.getByRole('heading', { level: 1, name: /trusted connections/i })).toBeInTheDocument();
    expect(screen.getByText(/voluntary location sharing/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText(/elena rostova/i).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/live field coordination roster/i)).toBeInTheDocument();
    });
  });

  it('supports opening the invite modal and creating a new invitation code', async () => {
    renderWithProviders(<ConnectionsView />);

    const inviteBtn = screen.getByRole('button', { name: /invite connection/i });
    fireEvent.click(inviteBtn);

    expect(screen.getByText(/invite trusted connection/i)).toBeInTheDocument();
    const nameInput = screen.getByPlaceholderText(/elena rostova or partner/i);
    fireEvent.change(nameInput, { target: { value: 'Marcus Vance' } });

    const submitBtn = screen.getByRole('button', { name: /generate invite/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(connectionsApi.createInvite).toHaveBeenCalledWith('Marcus Vance');
      expect(screen.getByText('aur_1234abcd')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /copy link/i })).toBeInTheDocument();
    });
  });

  it('toggles voluntary location sharing', async () => {
    renderWithProviders(<ConnectionsView />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /stop sharing immediately/i })).toBeInTheDocument();
    });

    const stopBtn = screen.getByRole('button', { name: /stop sharing immediately/i });
    fireEvent.click(stopBtn);

    await waitFor(() => {
      expect(connectionsApi.toggleLocationSharing).toHaveBeenCalledWith({
        enabled: false,
        duration_minutes: 60,
      });
    });
  });
});
