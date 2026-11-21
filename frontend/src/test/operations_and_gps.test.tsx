/**
 * Operations & GPS Hub Integration Test.
 * Validates real-time geolocation acquisition, dispatch board,
 * staff roster, and field check-in logging.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { OperationsView } from '../features/operations/OperationsView';
import { renderWithProviders } from './test-utils';

describe('Operations & GPS Hub', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('renders operations hub header, KPI strip, and operational zones', () => {
    renderWithProviders(<OperationsView />);

    expect(screen.getByRole('heading', { level: 1, name: /operations & gps hub/i })).toBeInTheDocument();
    expect(screen.getByText(/active staff/i)).toBeInTheDocument();
    expect(screen.getByText(/open work orders/i)).toBeInTheDocument();
    expect(screen.getByText(/jobs in progress/i)).toBeInTheDocument();
    expect(screen.getByText(/geofenced operational zones/i)).toBeInTheDocument();
    expect(screen.getByText(/primary command hq/i)).toBeInTheDocument();
  });

  it('handles GPS geolocation acquisition with HTML5 Geolocation API', async () => {
    const mockGeolocation = {
      getCurrentPosition: vi.fn((success) => {
        success({
          coords: {
            latitude: 37.774929,
            longitude: -122.419416,
            accuracy: 12,
            altitude: 45,
            speed: null,
            heading: null,
          },
        });
      }),
    };
    Object.defineProperty(window.navigator, 'geolocation', {
      value: mockGeolocation,
      writable: true,
      configurable: true,
    });

    renderWithProviders(<OperationsView />);

    const updateGpsBtn = screen.getByRole('button', { name: /update gps fix/i });
    fireEvent.click(updateGpsBtn);

    await waitFor(() => {
      expect(mockGeolocation.getCurrentPosition).toHaveBeenCalled();
      expect(screen.getByText(/37.774929°/)).toBeInTheDocument();
      expect(screen.getByText(/-122.419416°/)).toBeInTheDocument();
    });
  });

  it('allows logging field activity and persists to list', async () => {
    renderWithProviders(<OperationsView />);

    const input = screen.getByPlaceholderText(/optional activity or milestone notes/i);
    fireEvent.change(input, { target: { value: 'Inspected perimeter sensor cluster' } });

    const submitBtn = screen.getByRole('button', { name: /record check-in with current gps/i });
    fireEvent.click(submitBtn);

    expect(screen.getByText('Inspected perimeter sensor cluster')).toBeInTheDocument();
  });
});
