/**
 * GPS Journey Recorder — AUREN Personal AI Command Center.
 * Handles continuous GPS tracking, noise filtering, offline persistence via IndexedDB,
 * telemetry metrics (distance, pace, altitude), team check-in arrival stamps, and route preview.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Play,
  Pause,
  Square,
  Trash2,
  Navigation,
  Activity,
  Gauge,
  Clock,
  Compass,
  CheckCircle2,
  AlertTriangle,
  Wifi,
  WifiOff,
  Building2,
  MapPin,
} from 'lucide-react';
import { GPSPoint, JourneyCreatePayload } from '../../api/journeys';
import {
  ActiveJourneyState,
  calculateHaversineDistance,
  clearActiveJourney,
  getActiveJourney,
  saveActiveJourney,
  saveCompletedOfflineJourney,
  shouldAcceptGPSPoint,
  syncOfflineJourneys,
} from '../../lib/offlineJourneys';
import { JourneyTrajectoryMap } from './JourneyTrajectoryMap';

interface JourneyRecorderProps {
  onJourneySaved?: () => void;
}

export const JourneyRecorder: React.FC<JourneyRecorderProps> = ({ onJourneySaved }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isOnline, setIsOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);

  // Telemetry metrics
  const [distanceMeters, setDistanceMeters] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [currentSpeedKmh, setCurrentSpeedKmh] = useState(0);
  const [currentAltitude, setCurrentAltitude] = useState<number | null>(null);
  const [gpsAccuracy, setGpsAccuracy] = useState<number | null>(null);
  const [points, setPoints] = useState<GPSPoint[]>([]);
  const [currentFix, setCurrentFix] = useState<GPSPoint | null>(null);

  // Metadata & Team Assignment
  const [journeyTitle, setJourneyTitle] = useState('New GPS Journey');
  const [isTeamAssignment, setIsTeamAssignment] = useState(false);
  const [assignmentSite, setAssignmentSite] = useState('');
  const [assignmentPurpose, setAssignmentPurpose] = useState('');
  const [assignmentNotes, setAssignmentNotes] = useState('');
  const [checkInTime, setCheckInTime] = useState<string | null>(null);
  const [checkInCoords, setCheckInCoords] = useState<string | null>(null);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string>('');

  const watchIdRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Monitor online / offline network state
  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Restore existing active journey from IndexedDB on initial mount
  useEffect(() => {
    async function restoreActive() {
      const active = await getActiveJourney();
      if (active) {
        setJourneyTitle(active.title);
        setIsRecording(true);
        setIsPaused(active.status === 'paused');
        setDistanceMeters(active.distanceMeters || 0);
        setElapsedSeconds(active.durationSeconds || 0);
        setPoints(active.points || []);
        setIsTeamAssignment(active.isTeamAssignment || false);
        setAssignmentSite(active.assignmentSite || '');
        setAssignmentPurpose(active.assignmentPurpose || '');
        setAssignmentNotes(active.assignmentNotes || '');
        setCheckInTime(active.checkInTime || null);
        setCheckInCoords(active.checkInCoords || null);
        setIdempotencyKey(active.idempotencyKey || `jrn_${Date.now()}`);
        if (active.points.length > 0) {
          setCurrentFix(active.points[active.points.length - 1]);
        }
      }
    }
    restoreActive();
  }, []);

  // Second ticker timer
  useEffect(() => {
    if (isRecording && !isPaused) {
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isRecording, isPaused]);

  // Continuously persist active state to IndexedDB
  const persistActiveState = useCallback(
    async (updatedPoints: GPSPoint[], newDist: number) => {
      const state: ActiveJourneyState = {
        id: idempotencyKey,
        title: journeyTitle,
        status: isPaused ? 'paused' : 'recording',
        startedAt: new Date().toISOString(),
        isTeamAssignment,
        assignmentSite,
        assignmentPurpose,
        assignmentNotes,
        checkInTime: checkInTime || undefined,
        checkInCoords: checkInCoords || undefined,
        points: updatedPoints,
        distanceMeters: Math.round(newDist * 10) / 10,
        durationSeconds: elapsedSeconds,
        avgSpeedKmh: elapsedSeconds > 0 ? Number(((newDist / elapsedSeconds) * 3.6).toFixed(1)) : 0,
        idempotencyKey,
      };
      await saveActiveJourney(state);
    },
    [
      idempotencyKey,
      journeyTitle,
      isPaused,
      isTeamAssignment,
      assignmentSite,
      assignmentPurpose,
      assignmentNotes,
      checkInTime,
      checkInCoords,
      elapsedSeconds,
    ]
  );

  // Process incoming GPS fix
  const handleGpsPosition = useCallback(
    (pos: GeolocationPosition) => {
      const lat = Number(pos.coords.latitude.toFixed(6));
      const lng = Number(pos.coords.longitude.toFixed(6));
      const accuracy = Number(pos.coords.accuracy.toFixed(1));
      const altitude = pos.coords.altitude !== null ? Math.round(pos.coords.altitude) : null;
      const speed = pos.coords.speed !== null ? Number(pos.coords.speed.toFixed(1)) : null;
      const heading = pos.coords.heading !== null ? Math.round(pos.coords.heading) : null;

      const newFix: GPSPoint = {
        lat,
        lng,
        accuracy,
        altitude,
        speed,
        heading,
        timestamp: new Date().toISOString(),
      };

      setCurrentFix(newFix);
      setGpsAccuracy(accuracy);
      if (altitude !== null) setCurrentAltitude(altitude);
      if (speed !== null) setCurrentSpeedKmh(Math.max(0, Number((speed * 3.6).toFixed(1))));

      // Only add point if recording and not paused
      if (!isRecording || isPaused) return;

      setPoints((prevPoints) => {
        const lastPoint = prevPoints.length > 0 ? prevPoints[prevPoints.length - 1] : null;

        // Apply noise & jitter filter
        if (!shouldAcceptGPSPoint(newFix, lastPoint)) {
          return prevPoints;
        }

        let delta = 0;
        if (lastPoint) {
          delta = calculateHaversineDistance(lastPoint.lat, lastPoint.lng, newFix.lat, newFix.lng);
        }

        const nextPoints = [...prevPoints, newFix];
        setDistanceMeters((prevDist) => {
          const totalDist = prevDist + delta;
          persistActiveState(nextPoints, totalDist);
          return totalDist;
        });

        return nextPoints;
      });
    },
    [isRecording, isPaused, persistActiveState]
  );

  // Start or Stop GPS watcher
  useEffect(() => {
    if (!navigator.geolocation) {
      setGpsError('Geolocation is not supported by your device or browser.');
      return;
    }

    if (isRecording && !isPaused) {
      setGpsError(null);
      watchIdRef.current = navigator.geolocation.watchPosition(
        handleGpsPosition,
        (err) => {
          if (err.code === err.PERMISSION_DENIED) {
            setGpsError('Location permission denied. Please allow access.');
          } else if (err.code === err.POSITION_UNAVAILABLE) {
            setGpsError('GPS signal unavailable. Move to open sky.');
          }
        },
        {
          enableHighAccuracy: true,
          maximumAge: 1000,
          timeout: 10000,
        }
      );
    } else if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }

    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
    };
  }, [isRecording, isPaused, handleGpsPosition]);

  // Controls
  const handleStart = () => {
    const key = `jrn_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
    setIdempotencyKey(key);
    setIsRecording(true);
    setIsPaused(false);
    setDistanceMeters(0);
    setElapsedSeconds(0);
    setPoints([]);
    setCheckInTime(null);
    setCheckInCoords(null);
  };

  const handlePauseToggle = () => {
    setIsPaused((prev) => !prev);
  };

  const handleConfirmCheckIn = () => {
    if (!currentFix) return;
    const nowIso = new Date().toISOString();
    const coordsStr = `${currentFix.lat.toFixed(5)}, ${currentFix.lng.toFixed(5)}`;
    setCheckInTime(nowIso);
    setCheckInCoords(coordsStr);
    persistActiveState(points, distanceMeters);
  };

  const handleFinish = async () => {
    const avgSpeed =
      elapsedSeconds > 0
        ? Number(((distanceMeters / elapsedSeconds) * 3.6).toFixed(1))
        : 0;

    const payload: JourneyCreatePayload = {
      title: journeyTitle || 'Recorded GPS Journey',
      status: 'completed',
      distance_meters: Math.round(distanceMeters * 10) / 10,
      duration_seconds: elapsedSeconds,
      avg_speed_kmh: avgSpeed,
      is_offline_recorded: !isOnline,
      is_team_assignment: isTeamAssignment,
      assignment_site: isTeamAssignment ? assignmentSite : undefined,
      assignment_purpose: isTeamAssignment ? assignmentPurpose : undefined,
      assignment_notes: isTeamAssignment ? assignmentNotes : undefined,
      check_in_time: checkInTime || undefined,
      check_in_coords: checkInCoords || undefined,
      points,
      idempotency_key: idempotencyKey,
      completed_at: new Date().toISOString(),
    };

    // Save locally first to prevent any data loss
    await saveCompletedOfflineJourney(payload);
    await clearActiveJourney();

    // Reset local recording state
    setIsRecording(false);
    setIsPaused(false);
    setPoints([]);
    setDistanceMeters(0);
    setElapsedSeconds(0);
    setCheckInTime(null);
    setCheckInCoords(null);

    // If online, immediately sync to backend
    if (isOnline) {
      await syncOfflineJourneys();
    }

    if (onJourneySaved) {
      onJourneySaved();
    }
  };

  const handleDiscard = async () => {
    if (window.confirm('Discard current journey recording? Recorded coordinates will be deleted.')) {
      await clearActiveJourney();
      setIsRecording(false);
      setIsPaused(false);
      setPoints([]);
      setDistanceMeters(0);
      setElapsedSeconds(0);
      setCheckInTime(null);
      setCheckInCoords(null);
    }
  };

  // Format elapsed time (HH:MM:SS)
  const formatTimer = (totalSec: number) => {
    const hrs = Math.floor(totalSec / 3600);
    const mins = Math.floor((totalSec % 3600) / 60);
    const secs = totalSec % 60;
    return `${hrs > 0 ? `${hrs.toString().padStart(2, '0')}:` : ''}${mins
      .toString()
      .padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-5">
      {/* Top Controller Bar */}
      <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-amber-400 mb-1">
            <Navigation className="w-3.5 h-3.5 animate-spin" />
            <span>GPS Tracking Engine</span>
            <span className="text-slate-600">&bull;</span>
            {isOnline ? (
              <span className="text-emerald-400 flex items-center space-x-1">
                <Wifi className="w-3 h-3" />
                <span>Online</span>
              </span>
            ) : (
              <span className="text-amber-400 flex items-center space-x-1">
                <WifiOff className="w-3 h-3" />
                <span>Offline Safe</span>
              </span>
            )}
          </div>
          <input
            type="text"
            value={journeyTitle}
            onChange={(e) => setJourneyTitle(e.target.value)}
            disabled={isRecording}
            className="text-lg sm:text-xl font-bold text-white bg-transparent border-b border-transparent hover:border-white/20 focus:border-amber-400 focus:outline-none transition w-full max-w-md"
            placeholder="Journey Title..."
          />
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {!isRecording ? (
            <button
              onClick={handleStart}
              className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white font-semibold text-xs tracking-wide transition shadow-lg shadow-emerald-500/25 active:scale-95 cursor-pointer"
            >
              <Play className="w-4 h-4 fill-current" />
              <span>Start Journey</span>
            </button>
          ) : (
            <>
              <button
                onClick={handlePauseToggle}
                className={`flex items-center space-x-2 px-4 py-2.5 rounded-xl font-semibold text-xs transition cursor-pointer ${
                  isPaused
                    ? 'bg-amber-500 hover:bg-amber-400 text-black'
                    : 'bg-white/10 hover:bg-white/15 text-white'
                }`}
              >
                {isPaused ? <Play className="w-4 h-4 fill-current" /> : <Pause className="w-4 h-4" />}
                <span>{isPaused ? 'Resume' : 'Pause'}</span>
              </button>

              <button
                onClick={handleFinish}
                className="flex items-center space-x-2 px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-semibold text-xs transition shadow-lg shadow-amber-500/20 active:scale-95 cursor-pointer"
              >
                <Square className="w-4 h-4 fill-current" />
                <span>Finish & Sync</span>
              </button>

              <button
                onClick={handleDiscard}
                className="p-2.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 transition cursor-pointer"
                title="Discard Journey"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </div>

      {gpsError && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{gpsError}</span>
        </div>
      )}

      {/* Real-time GPS Telemetry Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {/* Distance */}
        <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Distance</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold font-mono text-white mt-1">
            {distanceMeters >= 1000
              ? `${(distanceMeters / 1000).toFixed(2)} km`
              : `${Math.round(distanceMeters)} m`}
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">Accurate Haversine filter</span>
        </div>

        {/* Elapsed Time */}
        <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Duration</span>
            <Clock className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold font-mono text-white mt-1">
            {formatTimer(elapsedSeconds)}
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">
            {isPaused ? 'Recording Paused' : isRecording ? 'Active Timer' : 'Standby'}
          </span>
        </div>

        {/* Speed */}
        <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Speed</span>
            <Gauge className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold font-mono text-white mt-1">
            {currentSpeedKmh} <span className="text-xs font-normal text-slate-400">km/h</span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">
            Avg:{' '}
            {elapsedSeconds > 0
              ? `${((distanceMeters / elapsedSeconds) * 3.6).toFixed(1)} km/h`
              : '0.0 km/h'}
          </span>
        </div>

        {/* Accuracy & Altitude */}
        <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Signal Accuracy</span>
            <Compass className="w-4 h-4 text-purple-400" />
          </div>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-2xl sm:text-3xl font-bold font-mono text-white">
              {gpsAccuracy !== null ? `±${Math.round(gpsAccuracy)}m` : 'Acquiring'}
            </span>
            {currentAltitude !== null && (
              <span className="text-xs font-mono text-slate-400">
                ({currentAltitude}m alt)
              </span>
            )}
          </div>
          <span
            className={`text-[10px] font-medium mt-1 block ${
              gpsAccuracy && gpsAccuracy <= 6
                ? 'text-emerald-400'
                : gpsAccuracy && gpsAccuracy <= 15
                ? 'text-amber-400'
                : 'text-slate-400'
            }`}
          >
            {gpsAccuracy && gpsAccuracy <= 6
              ? 'Excellent satellite lock'
              : gpsAccuracy && gpsAccuracy <= 15
              ? 'Good precision'
              : 'Moderate / Weak signal'}
          </span>
        </div>
      </div>

      {/* Vector Trajectory Radar Canvas */}
      <JourneyTrajectoryMap
        points={points}
        currentLocation={currentFix}
        height={300}
      />

      {/* Team Assignment & Site Check-in Section */}
      <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 sm:p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Building2 className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-white">Team Assignment & Site Check-In</h3>
          </div>

          <label className="flex items-center space-x-2 cursor-pointer text-xs text-slate-300">
            <input
              type="checkbox"
              checked={isTeamAssignment}
              onChange={(e) => setIsTeamAssignment(e.target.checked)}
              className="rounded bg-black/40 border-white/20 text-amber-400 focus:ring-amber-400"
            />
            <span>Tag as Field Assignment</span>
          </label>
        </div>

        {isTeamAssignment && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
            <div>
              <label className="block text-[11px] font-medium text-slate-400 uppercase tracking-wider mb-1">
                Destination Site / Asset Name
              </label>
              <input
                type="text"
                value={assignmentSite}
                onChange={(e) => setAssignmentSite(e.target.value)}
                placeholder="e.g. Sector 4 Solar Array"
                className="w-full px-3 py-2 rounded-xl bg-black/40 border border-white/10 text-xs text-white placeholder-slate-500 focus:border-amber-400 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-slate-400 uppercase tracking-wider mb-1">
                Assignment Purpose / Work Order ID
              </label>
              <input
                type="text"
                value={assignmentPurpose}
                onChange={(e) => setAssignmentPurpose(e.target.value)}
                placeholder="e.g. Routine Sensor Calibration / WO-8842"
                className="w-full px-3 py-2 rounded-xl bg-black/40 border border-white/10 text-xs text-white placeholder-slate-500 focus:border-amber-400 focus:outline-none"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-[11px] font-medium text-slate-400 uppercase tracking-wider mb-1">
                Field Dispatch Notes
              </label>
              <input
                type="text"
                value={assignmentNotes}
                onChange={(e) => setAssignmentNotes(e.target.value)}
                placeholder="Any special operational constraints or equipment tags..."
                className="w-full px-3 py-2 rounded-xl bg-black/40 border border-white/10 text-xs text-white placeholder-slate-500 focus:border-amber-400 focus:outline-none"
              />
            </div>

            {/* Check-In Arrival Button */}
            <div className="md:col-span-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-white/[0.06]">
              <div>
                {checkInTime ? (
                  <div className="flex items-center space-x-2 text-xs text-emerald-400">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span>
                      Site Check-In Verified at {new Date(checkInTime).toLocaleTimeString()} ({checkInCoords})
                    </span>
                  </div>
                ) : (
                  <span className="text-xs text-slate-500">
                    Record your voluntary arrival timestamp and coordinates when reaching the site.
                  </span>
                )}
              </div>

              <button
                type="button"
                onClick={handleConfirmCheckIn}
                disabled={!currentFix || Boolean(checkInTime)}
                className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium text-xs transition cursor-pointer"
              >
                <MapPin className="w-3.5 h-3.5" />
                <span>{checkInTime ? 'Arrival Confirmed' : 'Check-In at Location'}</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
