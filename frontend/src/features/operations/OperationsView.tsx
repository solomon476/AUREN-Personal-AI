/**
 * Operations & GPS Hub — AUREN Personal AI Command Center.
 * Unified operations center for live contextual location awareness,
 * GPS telemetry capture, field dispatch, crew roster, and work orders.
 * Elevated with AUREN Obsidian, Champagne Gold, Burgundy & Emerald Design System.
 */

import React, { useState } from 'react';
import {
  MapPin,
  Navigation,
  Users,
  Briefcase,
  Clock,
  Compass,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  RefreshCw,
  Radio,
} from 'lucide-react';

interface GPSCoordinate {
  latitude: number;
  longitude: number;
  accuracy: number;
  altitude: number | null;
  speed: number | null;
  heading: number | null;
  timestamp: string;
}

interface SavedZone {
  id: string;
  name: string;
  category: 'Home Base' | 'Headquarters' | 'Field Site' | 'Client Zone';
  lat: number;
  lng: number;
  radiusMeters: number;
}

interface StaffMember {
  id: string;
  name: string;
  role: string;
  status: 'On-Site' | 'In Transit' | 'Standby' | 'Off-Duty';
  currentZone: string;
  lastActive: string;
}

interface WorkOrder {
  id: string;
  title: string;
  priority: 'Urgent' | 'High' | 'Standard' | 'Low';
  status: 'In Progress' | 'Dispatched' | 'Completed' | 'Pending';
  assignee: string;
  location: string;
  dueTime: string;
}

interface FieldLog {
  id: string;
  timestamp: string;
  type: 'Check-In' | 'Milestone' | 'Check-Out';
  locationName: string;
  coords: string;
  notes: string;
}

const DEFAULT_ZONES: SavedZone[] = [
  { id: 'zone-1', name: 'Primary Command HQ', category: 'Headquarters', lat: 37.7749, lng: -122.4194, radiusMeters: 200 },
  { id: 'zone-2', name: 'Executive Base', category: 'Home Base', lat: 37.7833, lng: -122.4167, radiusMeters: 100 },
  { id: 'zone-3', name: 'Project Alpha Test Facility', category: 'Field Site', lat: 37.7650, lng: -122.4300, radiusMeters: 500 },
  { id: 'zone-4', name: 'Logistics Deployment Center', category: 'Client Zone', lat: 37.7500, lng: -122.4000, radiusMeters: 300 },
];

const INITIAL_STAFF: StaffMember[] = [
  { id: 'staff-1', name: 'Alex Mercer', role: 'Lead Field Specialist', status: 'On-Site', currentZone: 'Project Alpha Facility', lastActive: '4m ago' },
  { id: 'staff-2', name: 'Elena Rostova', role: 'Systems Engineer', status: 'In Transit', currentZone: 'En route to HQ', lastActive: '12m ago' },
  { id: 'staff-3', name: 'Marcus Vance', role: 'Field Operations Tech', status: 'On-Site', currentZone: 'Logistics Deployment', lastActive: 'Just now' },
  { id: 'staff-4', name: 'Jordan Reed', role: 'Quality & Safety Officer', status: 'Standby', currentZone: 'Command HQ', lastActive: '35m ago' },
];

const INITIAL_ORDERS: WorkOrder[] = [
  { id: 'WO-8041', title: 'Edge Hardware Sensor Diagnostics', priority: 'Urgent', status: 'In Progress', assignee: 'Alex Mercer', location: 'Project Alpha Facility', dueTime: 'Today, 16:30' },
  { id: 'WO-8042', title: 'Power Infrastructure Line Inspection', priority: 'High', status: 'Dispatched', assignee: 'Elena Rostova', location: 'Sector 4 Substation', dueTime: 'Today, 18:00' },
  { id: 'WO-8043', title: 'Telemetry Gateway Firmware Update', priority: 'Standard', status: 'Completed', assignee: 'Marcus Vance', location: 'Logistics Hub', dueTime: 'Completed 14:15' },
  { id: 'WO-8044', title: 'Perimeter Safety & Node Calibration', priority: 'Standard', status: 'Pending', assignee: 'Jordan Reed', location: 'Command HQ', dueTime: 'Tomorrow, 09:00' },
];

export const OperationsView: React.FC = () => {
  const [gpsData, setGpsData] = useState<GPSCoordinate | null>(() => {
    const saved = localStorage.getItem('auren_last_gps_fix');
    return saved ? JSON.parse(saved) : null;
  });
  const [isLocating, setIsLocating] = useState(false);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [staff] = useState<StaffMember[]>(INITIAL_STAFF);
  const [workOrders] = useState<WorkOrder[]>(INITIAL_ORDERS);
  const [fieldLogs, setFieldLogs] = useState<FieldLog[]>(() => {
    const saved = localStorage.getItem('auren_field_logs');
    return saved ? JSON.parse(saved) : [
      {
        id: 'log-1',
        timestamp: 'Today at 09:30 AM',
        type: 'Check-In',
        locationName: 'Primary Command HQ',
        coords: '37.7749° N, 122.4194° W',
        notes: 'Shift initialized. Telemetry feeds active.'
      }
    ];
  });
  const [newLogNotes, setNewLogNotes] = useState('');
  const [logType, setLogType] = useState<'Check-In' | 'Milestone' | 'Check-Out'>('Check-In');

  // Request high-accuracy GPS fix from HTML5 Geolocation API
  const handleAcquireLocation = () => {
    if (!navigator.geolocation) {
      setGpsError('Geolocation is not supported by your current browser.');
      return;
    }

    setIsLocating(true);
    setGpsError(null);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const fix: GPSCoordinate = {
          latitude: Number(pos.coords.latitude.toFixed(6)),
          longitude: Number(pos.coords.longitude.toFixed(6)),
          accuracy: Math.round(pos.coords.accuracy),
          altitude: pos.coords.altitude ? Math.round(pos.coords.altitude) : null,
          speed: pos.coords.speed !== null ? Number(pos.coords.speed.toFixed(1)) : null,
          heading: pos.coords.heading !== null ? Math.round(pos.coords.heading) : null,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        };
        setGpsData(fix);
        localStorage.setItem('auren_last_gps_fix', JSON.stringify(fix));
        setIsLocating(false);
      },
      (err) => {
        setIsLocating(false);
        if (err.code === err.PERMISSION_DENIED) {
          setGpsError('Location permission denied. Please allow location access in your browser settings.');
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          setGpsError('Location signal unavailable. Ensure GPS is enabled.');
        } else {
          setGpsError('GPS acquisition timed out. Try again in an open space.');
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0,
      }
    );
  };

  const handleAddLog = (e: React.FormEvent) => {
    e.preventDefault();
    const locName = gpsData ? `Fix: ${gpsData.latitude}, ${gpsData.longitude}` : 'Manual Location Stamp';
    const coordsStr = gpsData ? `${gpsData.latitude}° N, ${gpsData.longitude}° W (±${gpsData.accuracy}m)` : 'GPS Unlinked';

    const newLog: FieldLog = {
      id: `log-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      type: logType,
      locationName: locName,
      coords: coordsStr,
      notes: newLogNotes.trim() || `${logType} recorded via field console`,
    };

    const updated = [newLog, ...fieldLogs];
    setFieldLogs(updated);
    localStorage.setItem('auren_field_logs', JSON.stringify(updated));
    setNewLogNotes('');
  };

  return (
    <div className="space-y-6 sm:space-y-8 animate-in fade-in duration-300 max-w-7xl mx-auto pb-12">
      {/* Top Header & Context Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div>
          <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-400 mb-1">
            <Radio className="w-4 h-4 animate-pulse" />
            <span className="tracking-tight uppercase">PolarPath Field Operations &bull; Live Telemetry</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Operations & GPS Hub</h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            Real-time contextual location awareness, field crew dispatch & work order coordination.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={handleAcquireLocation}
            disabled={isLocating}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 active:scale-95 text-white font-semibold text-xs transition shadow-md shadow-emerald-500/25 disabled:opacity-60 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLocating ? 'animate-spin' : ''}`} />
            <span>{isLocating ? 'Acquiring Satellites...' : 'Update GPS Fix'}</span>
          </button>
        </div>
      </div>

      {/* Operational KPI Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 sm:p-5 relative overflow-hidden group hover:border-emerald-500/40 transition">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Active Staff</span>
            <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold font-mono text-white mt-2">
            {staff.filter(s => s.status !== 'Off-Duty').length}
          </div>
          <span className="text-[11px] text-emerald-400 font-medium mt-1 block">3 Deployed On-Site</span>
        </div>

        <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 sm:p-5 relative overflow-hidden group hover:border-amber-500/40 transition">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Open Work Orders</span>
            <Briefcase className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold font-mono text-white mt-2">
            {workOrders.filter(w => w.status !== 'Completed').length}
          </div>
          <span className="text-[11px] text-amber-300 font-medium mt-1 block">1 Urgent Priority</span>
        </div>

        <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 sm:p-5 relative overflow-hidden group hover:border-indigo-500/40 transition">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Jobs In Progress</span>
            <Navigation className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold font-mono text-white mt-2">
            {workOrders.filter(w => w.status === 'In Progress').length}
          </div>
          <span className="text-[11px] text-indigo-300 font-medium mt-1 block">Telemetry syncing</span>
        </div>

        <div className="bg-[#0e111a] border border-white/[0.08] rounded-2xl p-4 sm:p-5 relative overflow-hidden group hover:border-emerald-500/40 transition">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Closed Today</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold font-mono text-white mt-2">
            {workOrders.filter(w => w.status === 'Completed').length}
          </div>
          <span className="text-[11px] text-emerald-400 font-medium mt-1 block">100% SLA compliance</span>
        </div>
      </div>

      {/* Main Grid: Location Telemetry & Crew Dispatch */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Location Radar & Work Orders */}
        <div className="lg:col-span-2 space-y-6">
          {/* GPS Coordinates & Live Location Card */}
          <div className="bg-[#0e111a] border border-white/[0.09] rounded-2xl p-5 sm:p-6 relative overflow-hidden shadow-lg">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
              <div className="flex items-center space-x-2.5">
                <div className="h-8 w-8 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                  <MapPin className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white tracking-tight">Real-Time Geolocation Awareness</h3>
                  <p className="text-xs text-slate-400">Precision GPS fix with strict client-side consent</p>
                </div>
              </div>

              {gpsData && (
                <a
                  href={`https://www.google.com/maps?q=${gpsData.latitude},${gpsData.longitude}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.08] text-xs text-slate-200 hover:text-white transition"
                >
                  <span>Open in Maps</span>
                  <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                </a>
              )}
            </div>

            {gpsError && (
              <div className="mb-4 p-3 rounded-xl bg-rose-950/40 border border-rose-800/50 text-rose-200 text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                <span>{gpsError}</span>
              </div>
            )}

            {gpsData ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-[#07080c] border border-white/[0.06] rounded-xl p-3.5 sm:p-4">
                <div>
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block">Latitude</span>
                  <span className="text-sm sm:text-base font-bold font-mono text-white">{gpsData.latitude}°</span>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block">Longitude</span>
                  <span className="text-sm sm:text-base font-bold font-mono text-white">{gpsData.longitude}°</span>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block">Accuracy</span>
                  <span className="text-sm sm:text-base font-bold font-mono text-emerald-400">&plusmn; {gpsData.accuracy}m</span>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block">Last Fix</span>
                  <span className="text-sm sm:text-base font-bold font-mono text-slate-200">{gpsData.timestamp}</span>
                </div>
              </div>
            ) : (
              <div className="py-8 px-4 text-center rounded-xl bg-[#07080c]/60 border border-dashed border-white/[0.1]">
                <Compass className="w-8 h-8 text-slate-500 mx-auto mb-2 animate-bounce" />
                <p className="text-xs text-slate-300 font-medium">No live GPS fix cached</p>
                <p className="text-[11px] text-slate-500 mt-0.5">Click &ldquo;Update GPS Fix&rdquo; to query satellite coordinates</p>
              </div>
            )}

            {/* Geofenced Zones Indicator */}
            <div className="mt-5 pt-4 border-t border-white/[0.06]">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold text-white">Geofenced Operational Zones</span>
                <span className="text-[10px] text-slate-400 font-mono">4 Perimeter Zones Active</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {DEFAULT_ZONES.map((zone) => (
                  <div
                    key={zone.id}
                    className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.12] transition"
                  >
                    <div className="min-w-0">
                      <span className="text-xs font-semibold text-white truncate block">{zone.name}</span>
                      <span className="text-[10px] text-slate-400">{zone.category} &bull; {zone.radiusMeters}m radius</span>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/40">
                      Secured
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Work Orders Dispatch Board */}
          <div className="bg-[#0e111a] border border-white/[0.09] rounded-2xl p-5 sm:p-6 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-2">
                <Briefcase className="w-4 h-4 text-amber-400" />
                <h3 className="text-base font-bold text-white tracking-tight">Field Work Orders</h3>
              </div>
              <span className="text-xs text-slate-400 font-medium">{workOrders.length} Total Jobs</span>
            </div>

            <div className="space-y-2.5">
              {workOrders.map((wo) => {
                const isUrgent = wo.priority === 'Urgent';
                const isHigh = wo.priority === 'High';
                const isCompleted = wo.status === 'Completed';

                return (
                  <div
                    key={wo.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-[#07080c] border border-white/[0.06] hover:border-white/[0.12] transition"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center space-x-2">
                        <span className="text-[11px] font-mono text-slate-400 font-semibold">{wo.id}</span>
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded-md border ${
                            isUrgent
                              ? 'bg-rose-950/80 text-rose-300 border-rose-800/50'
                              : isHigh
                              ? 'bg-amber-950/80 text-amber-300 border-amber-800/50'
                              : 'bg-slate-800/80 text-slate-300 border-slate-700/50'
                          }`}
                        >
                          {wo.priority}
                        </span>
                        <span className="text-xs font-semibold text-white truncate">{wo.title}</span>
                      </div>
                      <div className="flex items-center space-x-3 text-[11px] text-slate-400 mt-1">
                        <span>Staff: <strong className="text-slate-300">{wo.assignee}</strong></span>
                        <span>&bull;</span>
                        <span>Location: <strong className="text-slate-300">{wo.location}</strong></span>
                      </div>
                    </div>

                    <div className="flex items-center space-x-2 sm:self-center">
                      <span
                        className={`text-[10px] font-medium px-2 py-1 rounded-lg border ${
                          isCompleted
                            ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/40'
                            : 'bg-indigo-950/60 text-indigo-300 border-indigo-800/40'
                        }`}
                      >
                        {wo.status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Col: Staff Roster & Field Logger */}
        <div className="space-y-6">
          {/* Crew Roster Card */}
          <div className="bg-[#0e111a] border border-white/[0.09] rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-2">
                <Users className="w-4 h-4 text-emerald-400" />
                <h3 className="text-base font-bold text-white tracking-tight">Active Crew Roster</h3>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-800/40">
                Live
              </span>
            </div>

            <div className="space-y-3">
              {staff.map((member) => {
                const isOnSite = member.status === 'On-Site';
                const isTransit = member.status === 'In Transit';

                return (
                  <div
                    key={member.id}
                    className="p-3 rounded-xl bg-[#07080c] border border-white/[0.06] hover:border-white/[0.12] transition flex items-center justify-between"
                  >
                    <div>
                      <div className="flex items-center space-x-1.5">
                        <span className="text-xs font-bold text-white">{member.name}</span>
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            isOnSite ? 'bg-emerald-400' : isTransit ? 'bg-amber-400' : 'bg-slate-500'
                          }`}
                        />
                      </div>
                      <span className="text-[11px] text-slate-400 block">{member.role}</span>
                      <span className="text-[10px] text-slate-500 block mt-0.5">{member.currentZone}</span>
                    </div>

                    <div className="text-right">
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded-md border ${
                          isOnSite
                            ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/40'
                            : isTransit
                            ? 'bg-amber-950/60 text-amber-300 border-amber-800/40'
                            : 'bg-slate-800/60 text-slate-400 border-slate-700/40'
                        }`}
                      >
                        {member.status}
                      </span>
                      <span className="text-[9px] text-slate-500 block mt-1">{member.lastActive}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Mobile Field Activity Logger */}
          <div className="bg-[#0e111a] border border-white/[0.09] rounded-2xl p-5 shadow-lg">
            <div className="flex items-center space-x-2 mb-3">
              <Clock className="w-4 h-4 text-[#d7ba83]" />
              <h3 className="text-base font-bold text-white tracking-tight">Field Check-In Logger</h3>
            </div>
            <p className="text-xs text-slate-400 mb-4">
              Stamp on-site arrivals, milestone inspections, and job completions with verified GPS coordinates.
            </p>

            <form onSubmit={handleAddLog} className="space-y-3">
              <div className="grid grid-cols-3 gap-1.5 bg-[#07080c] p-1 rounded-xl border border-white/[0.06]">
                {(['Check-In', 'Milestone', 'Check-Out'] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setLogType(t)}
                    className={`py-1.5 text-center text-xs font-semibold rounded-lg transition cursor-pointer ${
                      logType === t
                        ? 'bg-emerald-500 text-white shadow-sm'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <input
                type="text"
                value={newLogNotes}
                onChange={(e) => setNewLogNotes(e.target.value)}
                placeholder="Optional activity or milestone notes..."
                className="w-full bg-[#07080c] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500/60"
              />

              <button
                type="submit"
                className="w-full py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 active:scale-95 text-white font-semibold text-xs transition shadow-md shadow-emerald-500/20 cursor-pointer"
              >
                Record {logType} with Current GPS
              </button>
            </form>

            {/* Recent Log History */}
            <div className="mt-4 pt-3 border-t border-white/[0.06] space-y-2 max-h-48 overflow-y-auto scrollbar-none">
              {fieldLogs.slice(0, 4).map((log) => (
                <div key={log.id} className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05] text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white">{log.type}</span>
                    <span className="text-[10px] text-slate-400 font-mono">{log.timestamp}</span>
                  </div>
                  <p className="text-[11px] text-slate-300 mt-0.5">{log.notes}</p>
                  <span className="text-[10px] text-emerald-400 font-mono block mt-0.5">{log.coords}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
