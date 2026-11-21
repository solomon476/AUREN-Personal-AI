/**
 * GPS Journey Recorder — AUREN Personal AI Command Center.
 * Handles continuous GPS tracking, noise filtering, destination route navigation (e.g. Kisii),
 * live peer location tracking, offline persistence via IndexedDB, telemetry metrics,
 * team check-in arrival stamps, and interactive world map view.
 */

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Play,
  Pause,
  Square,
  Trash2,
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
  Flag,
  Search,
  X,
  Users,
  Share2,
  Loader2,
  ChevronRight,
  Crosshair,
  UserPlus,
  Copy,
  Check,
  ExternalLink,
} from 'lucide-react';
import { GPSPoint, JourneyCreatePayload } from '../../api/journeys';
import { connectionsApi } from '../../api/connections';
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
import { JourneyTrajectoryMap, JourneyDestination, PeerLocation } from './JourneyTrajectoryMap';

const POPULAR_DESTINATIONS: JourneyDestination[] = [
  { name: 'Kisii', displayName: 'Kisii, Kenya', lat: -0.669412, lng: 34.767794 },
  { name: 'Nairobi', displayName: 'Nairobi CBD, Kenya', lat: -1.286389, lng: 36.817223 },
  { name: 'Mombasa', displayName: 'Mombasa, Kenya', lat: -4.043477, lng: 39.668206 },
  { name: 'Nakuru', displayName: 'Nakuru, Kenya', lat: -0.303099, lng: 36.080026 },
  { name: 'Eldoret', displayName: 'Eldoret, Kenya', lat: 0.514277, lng: 35.269780 },
  { name: 'Kisumu', displayName: 'Kisumu, Kenya', lat: -0.091702, lng: 34.767956 },
];

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

  // Destination & Travel Navigation State
  const [destination, setDestination] = useState<JourneyDestination | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchingDest, setIsSearchingDest] = useState(false);
  const [searchResults, setSearchResults] = useState<JourneyDestination[]>([]);
  const [isDestModalOpen, setIsDestModalOpen] = useState(false);

  // Peer Location Sharing & Map Focus State
  const [peers, setPeers] = useState<PeerLocation[]>([]);
  const [allConnections, setAllConnections] = useState<any[]>([]);
  const [isSharingLocation, setIsSharingLocation] = useState(false);
  const [focusTarget, setFocusTarget] = useState<{ lat: number; lng: number } | null>(null);
  const [isConnectionsModalOpen, setIsConnectionsModalOpen] = useState(false);
  const [modalInviteName, setModalInviteName] = useState('');
  const [modalGeneratedCode, setModalGeneratedCode] = useState<string | null>(null);
  const [isModalCreatingInvite, setIsModalCreatingInvite] = useState(false);
  const [hasCopiedModalCode, setHasCopiedModalCode] = useState(false);
  const [modalIncomingCode, setModalIncomingCode] = useState('');
  const [isModalAccepting, setIsModalAccepting] = useState(false);
  const [modalAcceptMsg, setModalAcceptMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const lastLocationSyncRef = useRef<number>(0);

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

  // Poll trusted connections for peers sharing location
  const fetchPeerLocations = useCallback(async () => {
    try {
      const res = await connectionsApi.list();
      if (res && res.items) {
        setAllConnections(res.items);
        const activePeers: PeerLocation[] = res.items
          .filter((c) => c.location_sharing_active && c.last_latitude && c.last_longitude)
          .map((c) => ({
            id: c.id,
            displayName: c.display_name,
            avatarInitials: c.avatar_initials,
            lat: c.last_latitude!,
            lng: c.last_longitude!,
            lastUpdated: c.last_location_updated_at,
          }));
        setPeers(activePeers);
      }
    } catch {
      // Quiet fail if offline or not signed in
    }
  }, []);

  useEffect(() => {
    fetchPeerLocations();
    const peerInterval = setInterval(fetchPeerLocations, 20000);
    return () => clearInterval(peerInterval);
  }, [fetchPeerLocations]);

  // Restore existing active journey from IndexedDB on mount
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

  // Broadcast user's live position to trusted connections (throttled every 15s)
  const broadcastLocationToPeers = useCallback(
    async (lat: number, lng: number, acc: number) => {
      if (!isSharingLocation) return;
      const now = Date.now();
      if (now - lastLocationSyncRef.current < 15000) return;
      lastLocationSyncRef.current = now;
      try {
        await connectionsApi.updateLiveLocation({ latitude: lat, longitude: lng, accuracy: acc });
      } catch {
        // Non-critical background sync
      }
    },
    [isSharingLocation]
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

      // Broadcast location if sharing is enabled
      broadcastLocationToPeers(lat, lng, accuracy);

      // Only record point if actively recording and not paused
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
    [isRecording, isPaused, persistActiveState, broadcastLocationToPeers]
  );

  // Start or Stop GPS watcher
  useEffect(() => {
    if (!navigator.geolocation) {
      setGpsError('Geolocation is not supported by your device or browser.');
      return;
    }

    // Always keep light watch for initial fix
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

    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
    };
  }, [handleGpsPosition]);

  // Destination Search via OpenStreetMap Nominatim
  const handleSearchDestination = async (query: string) => {
    setSearchQuery(query);
    if (!query.trim() || query.length < 2) {
      setSearchResults([]);
      return;
    }

    setIsSearchingDest(true);
    try {
      const resp = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=5`,
        { headers: { 'User-Agent': 'AUREN-GPS/1.0' } }
      );
      const data = await resp.json();
      if (Array.isArray(data)) {
        const formatted: JourneyDestination[] = data.map((item: any) => ({
          name: item.name || item.display_name.split(',')[0],
          displayName: item.display_name,
          lat: parseFloat(item.lat),
          lng: parseFloat(item.lon),
        }));
        setSearchResults(formatted);
      }
    } catch (err) {
      console.warn('Geocoding search failed:', err);
    } finally {
      setIsSearchingDest(false);
    }
  };

  const handleSelectDestination = (dest: JourneyDestination) => {
    setDestination(dest);
    setIsDestModalOpen(false);
    setSearchQuery('');
    setSearchResults([]);
    if (journeyTitle === 'New GPS Journey') {
      setJourneyTitle(`Trip to ${dest.name}`);
    }
  };

  // Calculate live remaining distance to destination
  const remainingDistanceMeters = useMemo(() => {
    if (!destination || !currentFix) return null;
    return calculateHaversineDistance(currentFix.lat, currentFix.lng, destination.lat, destination.lng);
  }, [destination, currentFix]);

  // Estimate Time of Arrival (ETA)
  const etaText = useMemo(() => {
    if (!remainingDistanceMeters) return null;
    // Use current speed if moving > 5 km/h, otherwise assume average travel speed of 60 km/h
    const effectiveSpeed = currentSpeedKmh > 5 ? currentSpeedKmh : 60;
    const hours = remainingDistanceMeters / 1000 / effectiveSpeed;
    const mins = Math.round(hours * 60);
    if (mins < 60) return `~${mins} mins`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return `~${h}h ${m}m`;
  }, [remainingDistanceMeters, currentSpeedKmh]);

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
      title: journeyTitle.trim() || 'GPS Journey',
      distance_meters: Math.round(distanceMeters * 10) / 10,
      duration_seconds: elapsedSeconds,
      avg_speed_kmh: avgSpeed,
      is_offline_recorded: !isOnline,
      is_team_assignment: isTeamAssignment,
      assignment_site: isTeamAssignment ? assignmentSite || undefined : undefined,
      assignment_purpose: isTeamAssignment ? assignmentPurpose || undefined : undefined,
      assignment_notes: isTeamAssignment ? assignmentNotes || undefined : undefined,
      check_in_time: isTeamAssignment ? checkInTime || undefined : undefined,
      check_in_coords: isTeamAssignment ? checkInCoords || undefined : undefined,
      points,
      idempotency_key: idempotencyKey,
    };

    try {
      await saveCompletedOfflineJourney(payload);
      await clearActiveJourney();

      if (isOnline) {
        await syncOfflineJourneys();
      }

      setIsRecording(false);
      setIsPaused(false);
      setDistanceMeters(0);
      setElapsedSeconds(0);
      setPoints([]);
      setDestination(null);

      if (onJourneySaved) {
        onJourneySaved();
      }
    } catch (err) {
      console.error('Failed saving completed journey:', err);
    }
  };

  const handleDiscard = async () => {
    if (window.confirm('Are you sure you want to discard this recorded journey?')) {
      await clearActiveJourney();
      setIsRecording(false);
      setIsPaused(false);
      setDistanceMeters(0);
      setElapsedSeconds(0);
      setPoints([]);
      setDestination(null);
    }
  };

  // Toggle live location sharing with peers
  const handleToggleSharing = async () => {
    const next = !isSharingLocation;
    setIsSharingLocation(next);
    try {
      await connectionsApi.toggleLocationSharing({ enabled: next, duration_minutes: 240 });
      if (next && currentFix) {
        await connectionsApi.updateLiveLocation({
          latitude: currentFix.lat,
          longitude: currentFix.lng,
          accuracy: currentFix.accuracy,
        });
      }
    } catch (err) {
      console.warn('Failed toggling location sharing:', err);
    }
  };

  const handleLocatePeer = (peer: { lat: number; lng: number }) => {
    setFocusTarget({ lat: peer.lat, lng: peer.lng });
    setIsConnectionsModalOpen(false);
  };

  const handleModalCreateInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!modalInviteName.trim() || isModalCreatingInvite) return;
    setIsModalCreatingInvite(true);
    try {
      const res = await connectionsApi.createInvite(modalInviteName.trim());
      setModalGeneratedCode(res.invite_code);
      await fetchPeerLocations();
    } catch (err: any) {
      console.warn('Invite creation issue:', err);
    } finally {
      setIsModalCreatingInvite(false);
    }
  };

  const handleModalAcceptInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!modalIncomingCode.trim() || isModalAccepting) return;
    setIsModalAccepting(true);
    setModalAcceptMsg(null);
    try {
      await connectionsApi.acceptInvite(modalIncomingCode.trim());
      setModalAcceptMsg({ type: 'success', text: 'Trusted connection accepted! You can now track each other.' });
      setModalIncomingCode('');
      await fetchPeerLocations();
    } catch (err: any) {
      setModalAcceptMsg({ type: 'error', text: err?.message || 'Invalid or expired invite code.' });
    } finally {
      setIsModalAccepting(false);
    }
  };

  const handleCopyInviteLink = (code: string) => {
    const inviteUrl = `${window.location.origin}/connections?invite=${code}`;
    navigator.clipboard?.writeText(inviteUrl);
    setHasCopiedModalCode(true);
    setTimeout(() => setHasCopiedModalCode(false), 2500);
  };

  const formatTimer = (totalSeconds: number) => {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    const hrs = Math.floor(mins / 60);
    const remMins = mins % 60;
    if (hrs > 0) {
      return `${hrs.toString().padStart(2, '0')}:${remMins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-4">
      {/* Network & Active State Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white border border-slate-200/90 rounded-2xl p-3.5 sm:p-4 shadow-sm">
        <div className="flex items-center space-x-2 sm:space-x-3 min-w-0 flex-1">
          <input
            type="text"
            value={journeyTitle}
            onChange={(e) => setJourneyTitle(e.target.value)}
            disabled={isRecording}
            placeholder="Journey Title..."
            className="text-base sm:text-lg font-bold text-slate-900 bg-transparent border-0 border-b border-transparent hover:border-slate-300 focus:border-emerald-600 focus:outline-none transition-colors w-full min-w-0 truncate"
          />
          {isRecording && (
            <span className="flex-shrink-0 flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 border border-rose-200 text-rose-700 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-rose-600 animate-ping" />
              <span>{isPaused ? 'PAUSED' : 'RECORDING'}</span>
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2 flex-shrink-0 self-end sm:self-auto">
          {/* Voluntary Location Sharing & Trusted Connections Button */}
          <button
            type="button"
            onClick={() => setIsConnectionsModalOpen(true)}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center space-x-1.5 transition cursor-pointer shadow-xs ${
              isSharingLocation
                ? 'bg-emerald-600 text-white shadow-emerald-600/20'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
            title="Manage live location sharing & trusted connections"
          >
            <Share2 className="w-3.5 h-3.5" />
            <span>{isSharingLocation ? 'Sharing Active' : 'Share Location'}</span>
            {peers.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-emerald-800 text-[10px] text-white font-bold ml-0.5">
                {peers.length}
              </span>
            )}
          </button>

          <div
            className={`flex items-center space-x-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${
              isOnline
                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                : 'bg-amber-50 text-amber-800 border-amber-200'
            }`}
          >
            {isOnline ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
            <span className="hidden xs:inline">{isOnline ? 'Online Sync' : 'Offline Recording'}</span>
          </div>
        </div>
      </div>

      {gpsError && (
        <div className="flex items-center space-x-2 p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-xl text-xs">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{gpsError}</span>
        </div>
      )}

      {/* Target Destination Bar (e.g. Travel to Kisii) */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Flag className="w-4 h-4 text-amber-500" />
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
              Target Destination & Travel Tracker
            </h4>
          </div>

          {destination ? (
            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={() => setIsDestModalOpen(true)}
                className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition cursor-pointer"
                title="Change Destination"
                aria-label="Change Destination"
              >
                <Search className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setDestination(null)}
                className="text-xs text-rose-600 hover:underline flex items-center space-x-1 cursor-pointer font-medium"
                title="Clear Destination"
                aria-label="Clear Destination"
              >
                <X className="w-3.5 h-3.5" />
                <span className="hidden xs:inline">Clear</span>
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setIsDestModalOpen(true)}
              className="p-2 rounded-xl bg-slate-100 hover:bg-emerald-50 text-slate-700 hover:text-emerald-700 border border-slate-200/80 transition cursor-pointer shadow-2xs flex items-center justify-center"
              title="Search Target Destination"
              aria-label="Search Target Destination"
            >
              <Search className="w-4 h-4" />
            </button>
          )}
        </div>

        {destination ? (
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 p-3.5 bg-amber-50/70 border border-amber-200/80 rounded-xl">
            <div className="sm:col-span-1">
              <span className="text-[10px] font-mono text-amber-900 block font-semibold uppercase">Destination</span>
              <span className="text-sm font-bold text-slate-900">{destination.name}</span>
              <p className="text-[10px] text-slate-500 truncate max-w-xs">{destination.displayName}</p>
            </div>

            <div>
              <span className="text-[10px] font-mono text-amber-900 block font-semibold uppercase">Distance Covered</span>
              <span className="text-base font-bold font-mono text-emerald-700">
                {distanceMeters >= 1000
                  ? `${(distanceMeters / 1000).toFixed(1)} km`
                  : `${Math.round(distanceMeters)} m`}
              </span>
            </div>

            <div>
              <span className="text-[10px] font-mono text-amber-900 block font-semibold uppercase">Remaining Distance</span>
              <span className="text-base font-bold font-mono text-amber-800">
                {remainingDistanceMeters !== null
                  ? remainingDistanceMeters >= 1000
                    ? `${(remainingDistanceMeters / 1000).toFixed(1)} km`
                    : `${Math.round(remainingDistanceMeters)} m`
                  : 'Calculating...'}
              </span>
            </div>

            <div>
              <span className="text-[10px] font-mono text-amber-900 block font-semibold uppercase">Est. Travel Time</span>
              <span className="text-base font-bold font-mono text-slate-900">{etaText || 'Calculating...'}</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs text-slate-500">Quick Targets:</span>
            {POPULAR_DESTINATIONS.map((preset) => (
              <button
                key={preset.name}
                type="button"
                onClick={() => handleSelectDestination(preset)}
                className="px-2.5 py-1 bg-slate-100 hover:bg-emerald-50 hover:text-emerald-700 hover:border-emerald-200 border border-slate-200 rounded-lg text-xs text-slate-700 transition cursor-pointer font-medium"
              >
                {preset.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Destination Picker Modal */}
      {isDestModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Flag className="w-5 h-5 text-amber-500" />
                <h3 className="font-bold text-slate-900">Set Travel Destination</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsDestModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => handleSearchDestination(e.target.value)}
                placeholder="Search city, town, or address (e.g. Kisii)..."
                autoFocus
                className="w-full pl-9 pr-4 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-emerald-600 focus:bg-white transition"
              />
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              {isSearchingDest && (
                <Loader2 className="w-4 h-4 text-emerald-600 animate-spin absolute right-3 top-3" />
              )}
            </div>

            {/* Quick Popular Presets */}
            <div>
              <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider mb-2">Popular Cities in Kenya</p>
              <div className="grid grid-cols-2 gap-2">
                {POPULAR_DESTINATIONS.map((preset) => (
                  <button
                    key={preset.name}
                    type="button"
                    onClick={() => handleSelectDestination(preset)}
                    className="p-2.5 text-left rounded-xl bg-slate-50 hover:bg-emerald-50 hover:border-emerald-200 border border-slate-200/80 transition cursor-pointer flex items-center justify-between group"
                  >
                    <div>
                      <p className="font-bold text-xs text-slate-800 group-hover:text-emerald-800">{preset.name}</p>
                      <p className="text-[10px] text-slate-500">Kenya</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-emerald-600" />
                  </button>
                ))}
              </div>
            </div>

            {/* Dynamic Search Results */}
            {searchResults.length > 0 && (
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Search Results</p>
                {searchResults.map((res, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSelectDestination(res)}
                    className="w-full text-left p-2.5 rounded-xl bg-slate-50 hover:bg-emerald-50 border border-slate-200/80 text-xs text-slate-800 transition cursor-pointer"
                  >
                    <p className="font-bold text-slate-900">{res.name}</p>
                    <p className="text-[10px] text-slate-500 truncate">{res.displayName}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Primary Telemetry HUD Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Distance */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[10px] font-mono uppercase tracking-wider font-semibold">Distance</span>
            <Activity className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="flex items-baseline space-x-1 mt-1">
            <span className="text-2xl sm:text-3xl font-bold font-mono text-slate-900">
              {distanceMeters >= 1000
                ? (distanceMeters / 1000).toFixed(2)
                : Math.round(distanceMeters)}
            </span>
            <span className="text-xs font-mono text-slate-500">
              {distanceMeters >= 1000 ? 'km' : 'm'}
            </span>
          </div>
          <span className="text-[10px] text-slate-400 mt-1 block">Accurate Haversine filter</span>
        </div>

        {/* Elapsed Time */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[10px] font-mono uppercase tracking-wider font-semibold">Duration</span>
            <Clock className="w-4 h-4 text-amber-500" />
          </div>
          <div className="mt-1">
            <span className="text-2xl sm:text-3xl font-bold font-mono text-slate-900">
              {formatTimer(elapsedSeconds)}
            </span>
          </div>
          <span className="text-[10px] text-slate-400 mt-1 block">
            {isRecording ? (isPaused ? 'Timer paused' : 'Live tracking') : 'Standby'}
          </span>
        </div>

        {/* Speed */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[10px] font-mono uppercase tracking-wider font-semibold">Speed</span>
            <Gauge className="w-4 h-4 text-blue-600" />
          </div>
          <div className="flex items-baseline space-x-1 mt-1">
            <span className="text-2xl sm:text-3xl font-bold font-mono text-slate-900">
              {currentSpeedKmh}
            </span>
            <span className="text-xs font-mono text-slate-500">km/h</span>
          </div>
          <span className="text-[10px] text-slate-400 mt-1 block">
            Avg: {elapsedSeconds > 0 ? ((distanceMeters / elapsedSeconds) * 3.6).toFixed(1) : '0.0'} km/h
          </span>
        </div>

        {/* Satellite Signal Precision */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[10px] font-mono uppercase tracking-wider font-semibold">Signal Accuracy</span>
            <Compass className="w-4 h-4 text-purple-600" />
          </div>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-2xl sm:text-3xl font-bold font-mono text-slate-900">
              {gpsAccuracy !== null ? `±${Math.round(gpsAccuracy)}m` : 'Acquiring'}
            </span>
            {currentAltitude !== null && (
              <span className="text-xs font-mono text-slate-500">({currentAltitude}m alt)</span>
            )}
          </div>
          <span
            className={`text-[10px] font-medium mt-1 block ${
              gpsAccuracy && gpsAccuracy <= 6
                ? 'text-emerald-700 font-semibold'
                : gpsAccuracy && gpsAccuracy <= 15
                ? 'text-amber-700'
                : 'text-slate-500'
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

      {/* Interactive World Map & GPS Canvas */}
      <JourneyTrajectoryMap
        points={points}
        currentLocation={currentFix}
        destination={destination}
        peerLocations={peers}
        focusLocation={focusTarget}
        height={320}
      />

      {/* Connected Peers Status Strip & Interactive Map Locator */}
      {peers.length > 0 ? (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <div className="h-8 w-8 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-700 font-bold">
                <Users className="w-4 h-4" />
              </div>
              <div>
                <p className="text-xs font-bold text-slate-900">
                  {peers.length} Trusted Connection{peers.length > 1 ? 's' : ''} on Live Map
                </p>
                <p className="text-[11px] text-slate-500">
                  Voluntary live location broadcasting active
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsConnectionsModalOpen(true)}
              className="text-xs font-semibold text-emerald-600 hover:text-emerald-700 cursor-pointer flex items-center space-x-1"
            >
              <Share2 className="w-3.5 h-3.5" />
              <span>Manage Sharing</span>
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
            {peers.map((peer) => {
              const distMeters = currentFix
                ? calculateHaversineDistance(currentFix.lat, currentFix.lng, peer.lat, peer.lng)
                : null;
              const distText =
                distMeters !== null
                  ? distMeters >= 1000
                    ? `${(distMeters / 1000).toFixed(1)} km away`
                    : `${Math.round(distMeters)} m away`
                  : 'Sharing live';

              return (
                <div
                  key={peer.id}
                  className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-200/90 hover:border-indigo-300 transition"
                >
                  <div className="flex items-center space-x-2.5 min-w-0">
                    <div className="relative">
                      <div className="h-8 w-8 rounded-full bg-indigo-600 text-white font-bold text-xs flex items-center justify-center">
                        {peer.avatarInitials}
                      </div>
                      <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 border border-white animate-pulse" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-slate-900 truncate">{peer.displayName}</p>
                      <p className="text-[10px] text-slate-500 font-mono flex items-center space-x-1">
                        <MapPin className="w-3 h-3 text-indigo-500" />
                        <span>{distText}</span>
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleLocatePeer(peer)}
                    className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-xs transition cursor-pointer shrink-0"
                    title={`Locate ${peer.displayName} on Map`}
                  >
                    <Crosshair className="w-3.5 h-3.5" />
                    <span>Locate on Map</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-3.5 flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2.5 text-slate-600">
            <Users className="w-4 h-4 text-slate-400" />
            <span>Connect with contacts to view live positions on this map.</span>
          </div>
          <button
            type="button"
            onClick={() => setIsConnectionsModalOpen(true)}
            className="text-xs font-semibold text-emerald-600 hover:text-emerald-700 cursor-pointer flex items-center space-x-1 shrink-0"
          >
            <UserPlus className="w-3.5 h-3.5" />
            <span>Share / Invite</span>
          </button>
        </div>
      )}

      {/* Controls Bar */}
      <div className="flex items-center justify-center space-x-3 bg-white border border-slate-200/90 rounded-2xl p-3 shadow-sm">
        {!isRecording ? (
          <button
            type="button"
            onClick={handleStart}
            className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-bold text-sm transition shadow-md shadow-emerald-600/25 cursor-pointer"
          >
            <Play className="w-4 h-4 fill-white" />
            <span>Start Journey</span>
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={handlePauseToggle}
              className={`flex items-center space-x-2 px-4 py-2.5 rounded-xl text-xs font-semibold transition cursor-pointer ${
                isPaused
                  ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                  : 'bg-amber-500 hover:bg-amber-400 text-white'
              }`}
            >
              {isPaused ? <Play className="w-4 h-4 fill-white" /> : <Pause className="w-4 h-4 fill-white" />}
              <span>{isPaused ? 'Resume' : 'Pause'}</span>
            </button>

            <button
              type="button"
              onClick={handleFinish}
              className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition cursor-pointer shadow-sm"
            >
              <Square className="w-4 h-4 fill-white" />
              <span>Finish Journey</span>
            </button>

            <button
              type="button"
              onClick={handleDiscard}
              className="p-2.5 rounded-xl text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition cursor-pointer"
              title="Discard journey"
              aria-label="Discard journey"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </>
        )}
      </div>

      {/* Team Assignment & Site Check-in Section */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-4 sm:p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Building2 className="w-4 h-4 text-slate-700" />
            <h3 className="text-sm font-bold text-slate-900">Team Assignment & Site Check-In</h3>
          </div>

          <label className="flex items-center space-x-2 cursor-pointer text-xs text-slate-600 font-medium">
            <input
              type="checkbox"
              checked={isTeamAssignment}
              onChange={(e) => setIsTeamAssignment(e.target.checked)}
              className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
            />
            <span>Tag as Field Assignment</span>
          </label>
        </div>

        {isTeamAssignment && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
            <div>
              <label className="block text-[11px] font-medium text-slate-600 uppercase tracking-wider mb-1">
                Destination Site / Asset Name
              </label>
              <input
                type="text"
                value={assignmentSite}
                onChange={(e) => setAssignmentSite(e.target.value)}
                placeholder="e.g. Sector 4 Solar Array"
                className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:border-emerald-600 focus:bg-white focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-slate-600 uppercase tracking-wider mb-1">
                Assignment Purpose / Work Order ID
              </label>
              <input
                type="text"
                value={assignmentPurpose}
                onChange={(e) => setAssignmentPurpose(e.target.value)}
                placeholder="e.g. Routine Sensor Calibration / WO-8842"
                className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:border-emerald-600 focus:bg-white focus:outline-none"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-[11px] font-medium text-slate-600 uppercase tracking-wider mb-1">
                Field Dispatch Notes
              </label>
              <input
                type="text"
                value={assignmentNotes}
                onChange={(e) => setAssignmentNotes(e.target.value)}
                placeholder="Any special operational constraints or equipment tags..."
                className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:border-emerald-600 focus:bg-white focus:outline-none"
              />
            </div>

            {/* Check-In Arrival Button */}
            <div className="md:col-span-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-slate-100">
              <div>
                {checkInTime ? (
                  <div className="flex items-center space-x-2 text-xs text-emerald-700 font-medium">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
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
                className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium text-xs transition cursor-pointer shadow-xs"
              >
                <MapPin className="w-3.5 h-3.5" />
                <span>{checkInTime ? 'Arrival Confirmed' : 'Check-In at Location'}</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Share Location & Trusted Connections Modal */}
      {isConnectionsModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-5 sm:p-6 space-y-5">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center space-x-2.5">
                <div className="h-9 w-9 rounded-xl bg-emerald-50 text-emerald-700 flex items-center justify-center font-bold">
                  <Share2 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-base">Share Location &amp; Connections</h3>
                  <p className="text-[11px] text-slate-500">
                    Voluntary GPS sharing and real-time peer map tracking
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsConnectionsModalOpen(false);
                  setModalGeneratedCode(null);
                  setModalAcceptMsg(null);
                }}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Live Location Broadcast Master Switch */}
            <div className={`p-4 rounded-xl border transition ${
              isSharingLocation
                ? 'bg-emerald-50/70 border-emerald-200'
                : 'bg-slate-50 border-slate-200'
            }`}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className={`w-2.5 h-2.5 rounded-full ${isSharingLocation ? 'bg-emerald-600 animate-ping' : 'bg-slate-400'}`} />
                    <span className="text-xs font-bold text-slate-900">
                      {isSharingLocation ? 'Live Location Broadcasting Active' : 'Location Sharing Disabled'}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {isSharingLocation
                      ? 'Your coordinates are voluntarily shared with your accepted connections.'
                      : 'Enable sharing so your trusted contacts can view where you are.'}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={handleToggleSharing}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition cursor-pointer shadow-xs ${
                    isSharingLocation
                      ? 'bg-rose-600 hover:bg-rose-500 text-white'
                      : 'bg-emerald-600 hover:bg-emerald-500 text-white'
                  }`}
                >
                  {isSharingLocation ? 'Stop Sharing' : 'Start Sharing'}
                </button>
              </div>
            </div>

            {/* Trusted Contacts List */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Trusted Contacts ({allConnections.length})
                </h4>
                <a
                  href="/connections"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-emerald-600 hover:underline flex items-center space-x-1"
                >
                  <span>Full Network</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>

              {allConnections.length > 0 ? (
                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {allConnections.map((conn) => {
                    const isBroadcasting = conn.location_sharing_active && conn.last_latitude && conn.last_longitude;
                    return (
                      <div
                        key={conn.id}
                        className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 border border-slate-200/90 text-xs"
                      >
                        <div className="flex items-center space-x-2.5 min-w-0">
                          <div className="h-7 w-7 rounded-full bg-slate-200 text-slate-700 font-bold text-[11px] flex items-center justify-center shrink-0">
                            {conn.avatar_initials}
                          </div>
                          <div className="min-w-0">
                            <p className="font-bold text-slate-900 truncate">{conn.display_name}</p>
                            <p className="text-[10px] text-slate-500 flex items-center space-x-1">
                              {isBroadcasting ? (
                                <span className="text-emerald-700 font-medium flex items-center space-x-1">
                                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-pulse inline-block" />
                                  <span>Sharing live location</span>
                                </span>
                              ) : (
                                <span>Not broadcasting</span>
                              )}
                            </p>
                          </div>
                        </div>

                        {isBroadcasting && (
                          <button
                            type="button"
                            onClick={() => handleLocatePeer({ lat: conn.last_latitude, lng: conn.last_longitude })}
                            className="flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-semibold transition cursor-pointer"
                          >
                            <Crosshair className="w-3 h-3" />
                            <span>Locate on Map</span>
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="p-3 bg-slate-50 border border-dashed border-slate-200 rounded-xl text-center text-xs text-slate-500">
                  No contacts connected yet. Generate an invite below to share your link.
                </div>
              )}
            </div>

            {/* Invite a Friend Form */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
              <div className="flex items-center space-x-1.5">
                <UserPlus className="w-4 h-4 text-emerald-600" />
                <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Invite New Connection
                </h4>
              </div>
              <p className="text-[11px] text-slate-500">
                Enter your friend or colleague&apos;s name to generate an invite code &amp; link.
              </p>

              {!modalGeneratedCode ? (
                <form onSubmit={handleModalCreateInvite} className="flex gap-2">
                  <input
                    type="text"
                    value={modalInviteName}
                    onChange={(e) => setModalInviteName(e.target.value)}
                    placeholder="Friend's Name (e.g. Elena, Alex)"
                    required
                    disabled={isModalCreatingInvite}
                    className="flex-1 px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-emerald-600"
                  />
                  <button
                    type="submit"
                    disabled={!modalInviteName.trim() || isModalCreatingInvite}
                    className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs transition cursor-pointer flex items-center space-x-1"
                  >
                    {isModalCreatingInvite ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <span>Generate Invite</span>
                    )}
                  </button>
                </form>
              ) : (
                <div className="p-3 bg-emerald-50/80 border border-emerald-200 rounded-xl space-y-2">
                  <p className="text-xs font-bold text-emerald-900">
                    Invite Code Created for &quot;{modalInviteName}&quot;!
                  </p>
                  <div className="flex items-center justify-between p-2 rounded-lg bg-white border border-emerald-200 font-mono text-xs font-bold text-slate-900">
                    <span>{modalGeneratedCode}</span>
                    <button
                      type="button"
                      onClick={() => handleCopyInviteLink(modalGeneratedCode)}
                      className="flex items-center space-x-1 text-emerald-700 hover:text-emerald-800 text-xs font-sans cursor-pointer font-semibold"
                    >
                      {hasCopiedModalCode ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{hasCopiedModalCode ? 'Link Copied!' : 'Copy Link'}</span>
                    </button>
                  </div>
                  <p className="text-[10px] text-slate-500">
                    Share this code or link. Once they enter it, you will see each other live on the map!
                  </p>
                </div>
              )}
            </div>

            {/* Accept Friend's Code Form */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2.5">
              <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                Enter Received Invite Code
              </h4>
              <p className="text-[11px] text-slate-500">
                Received a code from someone? Enter it below to mutually connect.
              </p>
              <form onSubmit={handleModalAcceptInvite} className="flex gap-2">
                <input
                  type="text"
                  value={modalIncomingCode}
                  onChange={(e) => setModalIncomingCode(e.target.value)}
                  placeholder="e.g. aur_9f4e21"
                  required
                  disabled={isModalAccepting}
                  className="flex-1 px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs text-slate-900 font-mono placeholder-slate-400 focus:outline-none focus:border-emerald-600"
                />
                <button
                  type="submit"
                  disabled={!modalIncomingCode.trim() || isModalAccepting}
                  className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white font-semibold text-xs transition cursor-pointer"
                >
                  {isModalAccepting ? 'Connecting...' : 'Connect'}
                </button>
              </form>

              {modalAcceptMsg && (
                <div className={`p-2 rounded-lg text-xs font-medium flex items-center space-x-1.5 ${
                  modalAcceptMsg.type === 'success' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'
                }`}>
                  {modalAcceptMsg.type === 'success' ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" /> : <AlertTriangle className="w-3.5 h-3.5 text-rose-600 shrink-0" />}
                  <span>{modalAcceptMsg.text}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
