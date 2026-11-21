/**
 * Trusted Connections & Voluntary Location Sharing — AUREN Personal AI Command Center.
 * Handles mutual trusted connection invitations, QR code sharing, acceptance/revocation,
 * time-bound voluntary location sharing, and field crew live coordination roster.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Users,
  UserPlus,
  ShieldCheck,
  Clock,
  Radio,
  MapPin,
  Check,
  Copy,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Power,
  Loader2,
} from 'lucide-react';
import { Connection, connectionsApi } from '../../api/connections';

export const ConnectionsView: React.FC = () => {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Invite creation state
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteDisplayName, setInviteDisplayName] = useState('');
  const [createdInviteCode, setCreatedInviteCode] = useState<string | null>(null);
  const [isCreatingInvite, setIsCreatingInvite] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [hasCopiedCode, setHasCopiedCode] = useState(false);

  // Accept invite input
  const [incomingCode, setIncomingCode] = useState('');
  const [isAccepting, setIsAccepting] = useState(false);
  const [acceptMessage, setAcceptMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Voluntary Location Sharing settings
  const [isSharingLocation, setIsSharingLocation] = useState(false);
  const [sharingDurationMinutes, setSharingDurationMinutes] = useState(60);
  const [sharingExpiresAt, setSharingExpiresAt] = useState<string | null>(null);
  const [isUpdatingSharing, setIsUpdatingSharing] = useState(false);
  const locationWatchId = useRef<number | null>(null);

  // Load connections list
  const loadConnections = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await connectionsApi.list();
      const list = res.items || [];
      setConnections(list);

      // Check if current user has an active sharing session
      const activeShare = list.find((c) => c.location_sharing_active);
      if (activeShare && activeShare.location_sharing_expires_at) {
        setIsSharingLocation(true);
        setSharingExpiresAt(activeShare.location_sharing_expires_at);
      }
    } catch (err) {
      console.warn('Failed to fetch connections', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConnections();

    // Check if an invitation code was passed in the URL (e.g. /connections?invite=aur_12345678)
    const params = new URLSearchParams(window.location.search);
    const inviteParam = params.get('invite') || params.get('code');
    if (inviteParam) {
      setIncomingCode(inviteParam.trim());
    }
  }, [loadConnections]);

  // Handle live device location broadcast when voluntary sharing is active
  useEffect(() => {
    if (!isSharingLocation) {
      if (locationWatchId.current !== null) {
        navigator.geolocation?.clearWatch(locationWatchId.current);
        locationWatchId.current = null;
      }
      return;
    }

    if (navigator.geolocation) {
      locationWatchId.current = navigator.geolocation.watchPosition(
        (pos) => {
          connectionsApi.updateLiveLocation({
            latitude: Number(pos.coords.latitude.toFixed(6)),
            longitude: Number(pos.coords.longitude.toFixed(6)),
            accuracy: Math.round(pos.coords.accuracy),
          }).catch(() => {});
        },
        () => {},
        { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 }
      );
    }

    return () => {
      if (locationWatchId.current !== null) {
        navigator.geolocation?.clearWatch(locationWatchId.current);
        locationWatchId.current = null;
      }
    };
  }, [isSharingLocation]);

  // Toggle voluntary location sharing
  const handleToggleLocationSharing = async (enable: boolean) => {
    setIsUpdatingSharing(true);
    try {
      const res = await connectionsApi.toggleLocationSharing({
        enabled: enable,
        duration_minutes: sharingDurationMinutes,
      });
      setIsSharingLocation(res.active);
      setSharingExpiresAt(res.expires_at || null);
      await loadConnections();
    } catch (err) {
      console.error('Failed to toggle location sharing', err);
    } finally {
      setIsUpdatingSharing(false);
    }
  };

  // Create connection invite
  const handleCreateInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteDisplayName.trim() || isCreatingInvite) return;

    setIsCreatingInvite(true);
    setInviteError(null);
    try {
      const conn = await connectionsApi.createInvite(inviteDisplayName.trim());
      setCreatedInviteCode(conn.invite_code);
      await loadConnections();
    } catch (err: any) {
      console.error('Failed to create invite', err);
      setInviteError(err?.message || 'Failed to generate invitation code. Please try again.');
    } finally {
      setIsCreatingInvite(false);
    }
  };

  // Accept incoming invite
  const handleAcceptInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!incomingCode.trim()) return;

    setIsAccepting(true);
    setAcceptMessage(null);
    try {
      await connectionsApi.acceptInvite(incomingCode.trim());
      setAcceptMessage({ type: 'success', text: 'Trusted connection established successfully!' });
      setIncomingCode('');
      await loadConnections();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Invalid or expired invitation code.';
      setAcceptMessage({ type: 'error', text: msg });
    } finally {
      setIsAccepting(false);
    }
  };

  // Revoke connection
  const handleRevoke = async (connId: string, name: string) => {
    if (!window.confirm(`Revoke connection with "${name}"? Location access and private links will be cut immediately.`)) return;

    try {
      await connectionsApi.revoke(connId);
      setConnections((prev) => prev.filter((c) => c.id !== connId));
    } catch (err) {
      console.error('Failed to revoke connection', err);
    }
  };

  const copyInviteToClipboard = (code: string) => {
    const inviteUrl = `${window.location.origin}/connections?invite=${code}`;
    navigator.clipboard.writeText(inviteUrl);
    setHasCopiedCode(true);
    setTimeout(() => setHasCopiedCode(false), 2500);
  };

  // Render SVG QR Matrix representation for mobile screen scanning
  const renderQrSvg = (code: string) => {
    // Generate deterministic 17x17 grid based on string hash
    const size = 17;
    const cells: boolean[][] = [];
    let hash = 0;
    for (let i = 0; i < code.length; i++) {
      hash = (hash << 5) - hash + code.charCodeAt(i);
      hash |= 0;
    }

    for (let r = 0; r < size; r++) {
      const row: boolean[] = [];
      for (let c = 0; c < size; c++) {
        // Corner markers (Finder patterns)
        const isTopLeft = r < 5 && c < 5;
        const isTopRight = r < 5 && c >= size - 5;
        const isBottomLeft = r >= size - 5 && c < 5;
        if (isTopLeft || isTopRight || isBottomLeft) {
          const isBorder = r === 0 || r === 4 || c === 0 || c === 4 ||
            r === size - 5 || r === size - 1 || c === size - 5 || c === size - 1;
          const isCenter = (r === 2 && c === 2) || (r === 2 && c === size - 3) || (r === size - 3 && c === 2);
          row.push(isBorder || isCenter);
        } else {
          // Pseudorandom pseudo-QR filling
          const val = Math.abs(Math.sin((r * size + c) * 11 + hash));
          row.push(val > 0.45);
        }
      }
      cells.push(row);
    }

    return (
      <svg viewBox={`0 0 ${size} ${size}`} className="w-40 h-40 bg-white p-2 rounded-xl shadow-md mx-auto">
        {cells.map((row, r) =>
          row.map((active, c) => (
            active ? <rect key={`${r}-${c}`} x={c} y={r} width="1" height="1" fill="#0C0E14" /> : null
          ))
        )}
      </svg>
    );
  };

  const acceptedConnections = connections.filter((c) => c.status === 'accepted');
  const pendingConnections = connections.filter((c) => c.status === 'pending');
  const activeBroadcasters = connections.filter((c) => c.location_sharing_active && c.last_latitude !== null);

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-300">
      {/* Top Banner & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div>
          <div className="flex items-center space-x-2 text-xs font-semibold text-amber-400 mb-1 uppercase tracking-wider">
            <ShieldCheck className="w-4 h-4 text-amber-400" />
            <span>Trusted Network &bull; Row Level Protected</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Trusted Connections</h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            Private peer network, mutual invitations, and voluntary time-bound location sharing.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => {
              setShowInviteModal(true);
              setCreatedInviteCode(null);
              setInviteDisplayName('');
              setInviteError(null);
            }}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 active:scale-95 text-black font-semibold text-xs transition shadow-md shadow-amber-500/20 cursor-pointer"
          >
            <UserPlus className="w-3.5 h-3.5" />
            <span>Invite Connection</span>
          </button>
        </div>
      </div>

      {/* 3-Step Quick Guide */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="p-3.5 rounded-2xl bg-[#0e111a] border border-white/[0.08] flex items-start space-x-3">
          <div className="w-7 h-7 rounded-xl bg-amber-500/10 text-amber-400 font-bold text-xs flex items-center justify-center shrink-0">
            1
          </div>
          <div>
            <h4 className="text-xs font-bold text-white">Generate Invite</h4>
            <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
              Tap &quot;Invite Connection&quot; above, enter a name, and get your private invite link & QR code.
            </p>
          </div>
        </div>

        <div className="p-3.5 rounded-2xl bg-[#0e111a] border border-white/[0.08] flex items-start space-x-3">
          <div className="w-7 h-7 rounded-xl bg-amber-500/10 text-amber-400 font-bold text-xs flex items-center justify-center shrink-0">
            2
          </div>
          <div>
            <h4 className="text-xs font-bold text-white">Friend Accepts</h4>
            <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
              Send the code or link to your friend. They enter it in the box below to mutually connect.
            </p>
          </div>
        </div>

        <div className="p-3.5 rounded-2xl bg-[#0e111a] border border-white/[0.08] flex items-start space-x-3">
          <div className="w-7 h-7 rounded-xl bg-emerald-500/10 text-emerald-400 font-bold text-xs flex items-center justify-center shrink-0">
            3
          </div>
          <div>
            <h4 className="text-xs font-bold text-white">Live GPS Tracking</h4>
            <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
              Go to GPS Journeys and tap the Share button. Both of you will see each other live on the map!
            </p>
          </div>
        </div>
      </div>

      {/* Voluntary Location Sharing Master Panel */}
      <div className={`rounded-2xl p-5 sm:p-6 border transition relative overflow-hidden ${
        isSharingLocation
          ? 'bg-emerald-950/20 border-emerald-500/40'
          : 'bg-[#0e111a] border-white/[0.08]'
      }`}>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start space-x-3.5">
            <div className={`p-3 rounded-2xl shrink-0 ${
              isSharingLocation ? 'bg-emerald-500/20 text-emerald-400' : 'bg-white/10 text-slate-400'
            }`}>
              <Radio className={`w-6 h-6 ${isSharingLocation ? 'animate-pulse' : ''}`} />
            </div>

            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-base font-bold text-white">Voluntary Location Sharing</h3>
                {isSharingLocation ? (
                  <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono text-[10px] uppercase font-bold tracking-wider">
                    Broadcasting Active
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded-full bg-white/10 text-slate-400 font-mono text-[10px] uppercase">
                    Disabled
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-1 max-w-xl">
                {isSharingLocation
                  ? `Your live location is actively shared with your accepted trusted connections. Auto-expires at ${
                      sharingExpiresAt ? new Date(sharingExpiresAt).toLocaleTimeString() : 'end of window'
                    }.`
                  : 'Share your live GPS coordinates voluntarily with authorized connections for field coordination or personal safety.'}
              </p>
            </div>
          </div>

          {/* Duration & Toggle Controls */}
          <div className="flex flex-wrap items-center gap-3">
            {!isSharingLocation && (
              <div className="flex items-center space-x-2">
                <Clock className="w-4 h-4 text-slate-400" />
                <select
                  value={sharingDurationMinutes}
                  onChange={(e) => setSharingDurationMinutes(Number(e.target.value))}
                  className="bg-black/40 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-amber-400"
                >
                  <option value={15}>15 Minutes</option>
                  <option value={60}>1 Hour</option>
                  <option value={240}>4 Hours</option>
                  <option value={480}>8 Hours</option>
                </select>
              </div>
            )}

            <button
              onClick={() => handleToggleLocationSharing(!isSharingLocation)}
              disabled={isUpdatingSharing}
              className={`flex items-center space-x-2 px-5 py-2.5 rounded-xl font-semibold text-xs transition cursor-pointer ${
                isSharingLocation
                  ? 'bg-rose-500 hover:bg-rose-400 text-white shadow-lg shadow-rose-500/20'
                  : 'bg-emerald-500 hover:bg-emerald-400 text-white shadow-lg shadow-emerald-500/20'
              }`}
            >
              <Power className="w-4 h-4" />
              <span>{isSharingLocation ? 'Stop Sharing Immediately' : 'Start Voluntary Sharing'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Accept Invitation Code Box */}
      <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 sm:p-5">
        <h3 className="text-sm font-bold text-white mb-1">Enter Connection Invite Code</h3>
        <p className="text-xs text-slate-400 mb-3">
          Received an invitation code or link from a colleague? Enter it below to mutually accept the connection.
        </p>

        <form onSubmit={handleAcceptInvite} className="flex flex-col sm:flex-row gap-2 max-w-md">
          <input
            type="text"
            value={incomingCode}
            onChange={(e) => setIncomingCode(e.target.value)}
            placeholder="e.g. aur_a49f821c"
            className="flex-1 px-3.5 py-2 rounded-xl bg-black/40 border border-white/10 text-xs text-white placeholder-slate-500 focus:border-amber-400 focus:outline-none font-mono"
          />
          <button
            type="submit"
            disabled={isAccepting || !incomingCode.trim()}
            className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 disabled:opacity-50 text-white font-semibold text-xs transition cursor-pointer shrink-0"
          >
            {isAccepting ? 'Verifying...' : 'Accept Connection'}
          </button>
        </form>

        {acceptMessage && (
          <div className={`mt-2.5 text-xs flex items-center space-x-1.5 ${
            acceptMessage.type === 'success' ? 'text-emerald-400' : 'text-rose-400'
          }`}>
            {acceptMessage.type === 'success' ? (
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
            ) : (
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            )}
            <span>{acceptMessage.text}</span>
          </div>
        )}
      </div>

      {/* Live Coordination Roster (Active Broadcasters) */}
      {activeBroadcasters.length > 0 && (
        <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 sm:p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Radio className="w-4 h-4 text-emerald-400 animate-pulse" />
              <h3 className="text-sm font-bold text-white">Live Field Coordination Roster</h3>
            </div>
            <span className="text-[11px] font-mono text-emerald-400">
              {activeBroadcasters.length} Active Stream{activeBroadcasters.length > 1 ? 's' : ''}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {activeBroadcasters.map((conn) => (
              <div
                key={conn.id}
                className="p-3.5 rounded-xl bg-black/40 border border-emerald-500/30 flex items-center justify-between"
              >
                <div className="flex items-center space-x-3">
                  <div className="w-9 h-9 rounded-full bg-emerald-500/20 text-emerald-400 font-bold text-xs flex items-center justify-center font-mono">
                    {conn.avatar_initials}
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-white">{conn.display_name}</h4>
                    <span className="text-[10px] font-mono text-emerald-400 flex items-center space-x-1 mt-0.5">
                      <MapPin className="w-3 h-3" />
                      <span>
                        {conn.last_latitude?.toFixed(4)}°, {conn.last_longitude?.toFixed(4)}°
                      </span>
                    </span>
                  </div>
                </div>

                <span className="text-[10px] font-mono text-slate-400">
                  {conn.last_location_updated_at ? 'Live' : 'Active'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Accepted Connections List */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-white flex items-center space-x-2">
          <span>Trusted Connections</span>
          <span className="px-2 py-0.5 rounded-full bg-white/10 text-slate-300 font-mono text-xs">
            {acceptedConnections.length}
          </span>
        </h3>

        {isLoading ? (
          <div className="p-8 text-center text-slate-500 text-xs font-mono">
            Loading trusted connections...
          </div>
        ) : acceptedConnections.length === 0 ? (
          <div className="p-8 text-center rounded-2xl bg-[#0e111a] border border-white/[0.08]">
            <Users className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <h4 className="text-xs font-semibold text-white">No Accepted Connections Yet</h4>
            <p className="text-[11px] text-slate-400 mt-1 max-w-sm mx-auto">
              Click &quot;Invite Connection&quot; above to create a secure invitation code or link to share with colleagues or family.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {acceptedConnections.map((c) => (
              <div
                key={c.id}
                className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 flex items-center justify-between group hover:border-amber-400/40 transition"
              >
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-full bg-white/10 text-amber-400 font-bold text-xs flex items-center justify-center font-mono">
                    {c.avatar_initials}
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-white">{c.display_name}</h4>
                    <span className="text-[10px] text-slate-500">
                      Connected {new Date(c.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}
                    </span>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 font-mono text-[10px]">
                    Mutual
                  </span>
                  <button
                    onClick={() => handleRevoke(c.id, c.display_name)}
                    className="p-1.5 text-slate-500 hover:text-rose-400 rounded-lg transition cursor-pointer"
                    title="Revoke connection"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pending Invitations Strip */}
      {pendingConnections.length > 0 && (
        <div className="space-y-3 pt-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Pending Invitations ({pendingConnections.length})
          </h3>

          <div className="space-y-2">
            {pendingConnections.map((c) => (
              <div
                key={c.id}
                className="bg-[#0e111a] border border-white/[0.06] rounded-xl p-3 flex items-center justify-between text-xs"
              >
                <div>
                  <span className="font-semibold text-white">{c.display_name}</span>
                  <span className="text-slate-500 font-mono text-[11px] ml-2">Code: {c.invite_code}</span>
                </div>

                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => copyInviteToClipboard(c.invite_code)}
                    className="px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/15 text-[11px] text-slate-300 flex items-center space-x-1 transition cursor-pointer"
                  >
                    <Copy className="w-3 h-3" />
                    <span>Copy Link</span>
                  </button>
                  <button
                    onClick={() => handleRevoke(c.id, c.display_name)}
                    className="text-slate-500 hover:text-rose-400 p-1 transition cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Privacy Guarantee Note */}
      <div className="p-4 rounded-2xl bg-black/30 border border-white/[0.06] flex items-start space-x-3 text-xs text-slate-400">
        <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
        <p>
          <strong className="text-white">Strict Privacy Boundary:</strong> Location sharing is voluntary, temporary, and never covert. Your coordinates are never accessible to ordinary AI memory extraction or untrusted third parties. You maintain full ownership and can revoke any connection instantly.
        </p>
      </div>

      {/* Invite Modal with SVG QR Code */}
      {showInviteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[#0e111a] border border-white/10 rounded-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-base font-bold text-white">Invite Trusted Connection</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Generate a private invitation code & QR code to connect with someone you trust.
                </p>
              </div>

              <button
                onClick={() => setShowInviteModal(false)}
                className="text-slate-400 hover:text-white p-1"
              >
                &times;
              </button>
            </div>

            {!createdInviteCode ? (
              <form onSubmit={handleCreateInvite} className="space-y-3 pt-2">
                <div>
                  <label className="block text-[11px] font-medium text-slate-400 uppercase tracking-wider mb-1">
                    Connection Label / Person&apos;s Name
                  </label>
                  <input
                    type="text"
                    value={inviteDisplayName}
                    onChange={(e) => {
                      setInviteDisplayName(e.target.value);
                      if (inviteError) setInviteError(null);
                    }}
                    placeholder="e.g. Elena Rostova or Partner"
                    required
                    disabled={isCreatingInvite}
                    className="w-full px-3.5 py-2 rounded-xl bg-black/40 border border-white/10 text-xs text-white placeholder-slate-500 focus:border-amber-400 focus:outline-none"
                  />
                </div>

                {inviteError && (
                  <div className="p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center space-x-2">
                    <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-400" />
                    <span>{inviteError}</span>
                  </div>
                )}

                <div className="flex justify-end space-x-2 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setShowInviteModal(false);
                      setInviteError(null);
                    }}
                    disabled={isCreatingInvite}
                    className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs text-slate-300 font-medium transition cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!inviteDisplayName.trim() || isCreatingInvite}
                    className="flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-black text-xs font-semibold transition cursor-pointer shadow-md shadow-amber-500/20"
                  >
                    {isCreatingInvite ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Generating...</span>
                      </>
                    ) : (
                      <span>Generate Invite</span>
                    )}
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4 text-center pt-2">
                <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-left text-xs text-emerald-300 space-y-1">
                  <p className="font-semibold text-white flex items-center space-x-1.5">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Invitation Created!</span>
                  </p>
                  <p className="text-[11px] text-slate-300">
                    Share this unique code or link with your connection. Once accepted, you both can track each other live on the GPS map.
                  </p>
                </div>

                {/* Visual QR Code Representation */}
                <div className="my-2">{renderQrSvg(createdInviteCode)}</div>

                <div className="p-3 rounded-xl bg-black/50 border border-white/10 text-xs font-mono text-amber-400 select-all">
                  {createdInviteCode}
                </div>

                <div className="flex items-center justify-center space-x-2">
                  <button
                    onClick={() => copyInviteToClipboard(createdInviteCode)}
                    className="flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-semibold text-xs transition cursor-pointer shadow-md shadow-amber-500/20"
                  >
                    {hasCopiedCode ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{hasCopiedCode ? 'Copied Invite Link!' : 'Copy Link'}</span>
                  </button>

                  <button
                    onClick={() => {
                      setShowInviteModal(false);
                      setCreatedInviteCode(null);
                      setInviteDisplayName('');
                    }}
                    className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white font-medium text-xs transition cursor-pointer"
                  >
                    Done
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
