/**
 * GPS Journey History & Offline Sync Manager — AUREN Personal AI Command Center.
 * Displays both server-synced journeys and offline-recorded journeys pending sync.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  MapPin,
  RefreshCw,
  Trash2,
  CheckCircle2,
  Building2,
  Calendar,
  Eye,
  X,
} from 'lucide-react';
import { Journey, journeysApi } from '../../api/journeys';
import {
  getAllOfflineJourneys,
  OfflineJourneyRecord,
  subscribeToSyncUpdates,
  syncOfflineJourneys,
} from '../../lib/offlineJourneys';
import { JourneyTrajectoryMap } from './JourneyTrajectoryMap';

export const JourneyHistory: React.FC = () => {
  const [journeys, setJourneys] = useState<Journey[]>([]);
  const [offlineRecords, setOfflineRecords] = useState<OfflineJourneyRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [selectedJourney, setSelectedJourney] = useState<Journey | null>(null);

  // Load journeys from API and local IndexedDB
  const loadJourneys = useCallback(async () => {
    setIsLoading(true);
    try {
      const [apiRes, localRecords] = await Promise.all([
        journeysApi.list(1, 50).catch(() => ({ items: [], total: 0 })),
        getAllOfflineJourneys().catch(() => []),
      ]);

      setJourneys(apiRes.items || []);
      setOfflineRecords(localRecords || []);
    } catch (err) {
      console.warn('Failed to fetch journeys', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadJourneys();
    const unsubscribe = subscribeToSyncUpdates((status) => {
      setIsSyncing(status.isSyncing);
      if (!status.isSyncing) {
        loadJourneys();
      }
    });
    return () => unsubscribe();
  }, [loadJourneys]);

  const handleManualSync = async () => {
    setIsSyncing(true);
    await syncOfflineJourneys();
    await loadJourneys();
    setIsSyncing(false);
  };

  const handleDelete = async (journey: Journey) => {
    if (!window.confirm(`Are you sure you want to delete "${journey.title}"?`)) return;

    try {
      await journeysApi.delete(journey.id);
      setJourneys((prev) => prev.filter((j) => j.id !== journey.id));
      if (selectedJourney?.id === journey.id) {
        setSelectedJourney(null);
      }
    } catch {
      // If server delete fails (e.g. offline), filter out locally
      setJourneys((prev) => prev.filter((j) => j.id !== journey.id));
    }
  };

  // Combine offline pending items with synced items, deduping by idempotency_key or id
  const displayItems = React.useMemo(() => {
    const existingIds = new Set(journeys.map((j) => j.id));
    const existingKeys = new Set(journeys.map((j) => j.idempotency_key).filter(Boolean));

    const pendingAsJourneys: Journey[] = offlineRecords
      .filter((rec) => rec.syncStatus === 'pending' || rec.syncStatus === 'failed')
      .filter((rec) => !existingIds.has(rec.id) && !existingKeys.has(rec.payload.idempotency_key))
      .map((rec) => ({
        id: rec.id,
        user_id: 'local_user',
        title: rec.payload.title || 'Offline Journey',
        status: (rec.payload.status as Journey['status']) || 'completed',
        distance_meters: rec.payload.distance_meters || 0,
        duration_seconds: rec.payload.duration_seconds || 0,
        avg_speed_kmh: rec.payload.avg_speed_kmh || 0,
        is_offline_recorded: true,
        is_team_assignment: rec.payload.is_team_assignment || false,
        assignment_site: rec.payload.assignment_site,
        assignment_purpose: rec.payload.assignment_purpose,
        assignment_notes: rec.payload.assignment_notes,
        check_in_time: rec.payload.check_in_time,
        check_in_coords: rec.payload.check_in_coords,
        points: rec.payload.points || [],
        idempotency_key: rec.payload.idempotency_key,
        created_at: rec.updatedAt,
        completed_at: rec.payload.completed_at,
      }));

    return [...pendingAsJourneys, ...journeys];
  }, [journeys, offlineRecords]);

  const pendingCount = offlineRecords.filter((r) => r.syncStatus === 'pending').length;

  return (
    <div className="space-y-4">
      {/* Header & Sync Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center space-x-2">
            <span>Recorded GPS Journeys</span>
            <span className="px-2 py-0.5 rounded-full bg-white/10 text-slate-300 font-mono text-xs">
              {displayItems.length}
            </span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Historical GPS tracks, route logs, and offline synchronized records.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {pendingCount > 0 && (
            <span className="px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono">
              {pendingCount} Pending Sync
            </span>
          )}

          <button
            onClick={handleManualSync}
            disabled={isSyncing}
            className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-white/10 hover:bg-white/15 disabled:opacity-50 text-white font-medium text-xs transition cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
            <span>{isSyncing ? 'Syncing...' : 'Sync Pending'}</span>
          </button>
        </div>
      </div>

      {/* Journeys List */}
      {isLoading ? (
        <div className="p-8 text-center text-slate-500 text-xs font-mono">
          Loading recorded journeys...
        </div>
      ) : displayItems.length === 0 ? (
        <div className="p-12 text-center rounded-2xl bg-[#0e111a] border border-white/[0.08]">
          <MapPin className="w-8 h-8 text-slate-600 mx-auto mb-2" />
          <h3 className="text-sm font-semibold text-white">No Journeys Recorded Yet</h3>
          <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
            Use the Journey Recorder above to start tracking your route, speed, distance, and field assignments.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
          {displayItems.map((j) => {
            const isLocalPending = offlineRecords.some(
              (r) => (r.id === j.id || (j.idempotency_key && r.payload.idempotency_key === j.idempotency_key)) && r.syncStatus === 'pending'
            );

            return (
              <div
                key={j.id}
                className="bg-[#0e111a] border border-white/[0.08] hover:border-amber-400/40 rounded-2xl p-4 sm:p-5 transition flex flex-col justify-between group"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h4 className="text-sm font-bold text-white group-hover:text-amber-400 transition">
                        {j.title}
                      </h4>
                      <div className="flex items-center space-x-2 text-[11px] text-slate-400 mt-0.5">
                        <Calendar className="w-3 h-3 text-slate-500" />
                        <span>{new Date(j.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                        <span>&bull;</span>
                        <span>{new Date(j.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    </div>

                    {/* Status Badge */}
                    <div>
                      {isLocalPending ? (
                        <span className="px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-300 font-mono text-[10px] flex items-center space-x-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                          <span>Pending Sync</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-mono text-[10px] flex items-center space-x-1">
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          <span>Synced</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Field Assignment Pill */}
                  {j.is_team_assignment && (
                    <div className="mt-2.5 p-2 rounded-xl bg-black/40 border border-white/[0.06] text-xs flex items-center space-x-2 text-slate-300">
                      <Building2 className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                      <span className="truncate">
                        <strong>{j.assignment_site || 'Field Site'}</strong>: {j.assignment_purpose || 'Operational Assignment'}
                      </span>
                    </div>
                  )}

                  {/* Telemetry Stats */}
                  <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-white/[0.06] text-xs">
                    <div>
                      <span className="text-[10px] uppercase font-mono text-slate-400 block">Distance</span>
                      <span className="font-mono font-semibold text-white">
                        {j.distance_meters >= 1000
                          ? `${(j.distance_meters / 1000).toFixed(2)} km`
                          : `${Math.round(j.distance_meters)} m`}
                      </span>
                    </div>

                    <div>
                      <span className="text-[10px] uppercase font-mono text-slate-400 block">Duration</span>
                      <span className="font-mono font-semibold text-white">
                        {Math.floor(j.duration_seconds / 60)}m {j.duration_seconds % 60}s
                      </span>
                    </div>

                    <div>
                      <span className="text-[10px] uppercase font-mono text-slate-400 block">Avg Pace</span>
                      <span className="font-mono font-semibold text-white">
                        {j.avg_speed_kmh ? `${j.avg_speed_kmh} km/h` : '—'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Card Actions */}
                <div className="flex items-center justify-between gap-2 mt-4 pt-3 border-t border-white/[0.06]">
                  <button
                    onClick={() => setSelectedJourney(j)}
                    className="flex items-center space-x-1.5 text-xs text-amber-400 hover:text-amber-300 font-medium transition cursor-pointer"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>View Trajectory</span>
                  </button>

                  <button
                    onClick={() => handleDelete(j)}
                    className="text-slate-500 hover:text-rose-400 p-1 rounded transition cursor-pointer"
                    title="Delete journey"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Trajectory Modal View */}
      {selectedJourney && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[#0e111a] border border-white/10 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-5 sm:p-6 space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-bold text-white">{selectedJourney.title}</h3>
                <p className="text-xs text-slate-400">
                  Recorded on {new Date(selectedJourney.created_at).toLocaleString()}
                </p>
              </div>

              <button
                onClick={() => setSelectedJourney(null)}
                className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-slate-300 transition cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Trajectory Map Component */}
            <JourneyTrajectoryMap
              points={selectedJourney.points || []}
              height={260}
              showControls={true}
            />

            {/* Detailed Stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-black/40 p-3.5 rounded-xl border border-white/[0.06]">
              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block">Total Distance</span>
                <span className="text-sm font-bold font-mono text-white">
                  {selectedJourney.distance_meters >= 1000
                    ? `${(selectedJourney.distance_meters / 1000).toFixed(2)} km`
                    : `${Math.round(selectedJourney.distance_meters)} m`}
                </span>
              </div>

              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block">Elapsed Time</span>
                <span className="text-sm font-bold font-mono text-white">
                  {Math.floor(selectedJourney.duration_seconds / 60)}m {selectedJourney.duration_seconds % 60}s
                </span>
              </div>

              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block">Avg Speed</span>
                <span className="text-sm font-bold font-mono text-white">
                  {selectedJourney.avg_speed_kmh ? `${selectedJourney.avg_speed_kmh} km/h` : '—'}
                </span>
              </div>

              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block">GPS Fixes</span>
                <span className="text-sm font-bold font-mono text-white">
                  {selectedJourney.points?.length || 0}
                </span>
              </div>
            </div>

            {/* Team Assignment Metadata */}
            {selectedJourney.is_team_assignment && (
              <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs space-y-2">
                <div className="flex items-center space-x-1.5 text-amber-300 font-semibold">
                  <Building2 className="w-4 h-4" />
                  <span>Team Field Assignment Details</span>
                </div>
                {selectedJourney.assignment_site && (
                  <p className="text-slate-200">
                    <strong>Site:</strong> {selectedJourney.assignment_site}
                  </p>
                )}
                {selectedJourney.assignment_purpose && (
                  <p className="text-slate-200">
                    <strong>Purpose:</strong> {selectedJourney.assignment_purpose}
                  </p>
                )}
                {selectedJourney.check_in_time && (
                  <p className="text-emerald-400 flex items-center space-x-1">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>
                      Site Check-In recorded at {new Date(selectedJourney.check_in_time).toLocaleString()} ({selectedJourney.check_in_coords})
                    </span>
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
