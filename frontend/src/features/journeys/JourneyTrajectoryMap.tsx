/**
 * Offline-Capable Vector Trajectory Map for AUREN GPS Journeys.
 * Renders GPS coordinate breadcrumb paths onto a normalized 2D SVG canvas.
 * Works without internet, tiles, or external map API keys.
 */

import React, { useMemo } from 'react';
import { GPSPoint } from '../../api/journeys';
import { Compass, MapPin, Navigation } from 'lucide-react';

interface JourneyTrajectoryMapProps {
  points: GPSPoint[];
  currentLocation?: GPSPoint | null;
  height?: number;
  className?: string;
  showControls?: boolean;
}

export const JourneyTrajectoryMap: React.FC<JourneyTrajectoryMapProps> = ({
  points,
  currentLocation,
  height = 280,
  className = '',
  showControls = true,
}) => {
  // Combine recorded points with current fix if available
  const allPoints = useMemo(() => {
    if (!currentLocation) return points;
    if (points.length === 0) return [currentLocation];
    return points;
  }, [points, currentLocation]);

  const { pathData, startSvgPoint, endSvgPoint, hasPoints } = useMemo(() => {
    if (allPoints.length === 0) {
      return { pathData: '', startSvgPoint: null, endSvgPoint: null, hasPoints: false };
    }

    let minLat = Infinity;
    let maxLat = -Infinity;
    let minLng = Infinity;
    let maxLng = -Infinity;

    allPoints.forEach((p) => {
      if (p.lat < minLat) minLat = p.lat;
      if (p.lat > maxLat) maxLat = p.lat;
      if (p.lng < minLng) minLng = p.lng;
      if (p.lng > maxLng) maxLng = p.lng;
    });

    // Provide minimum dimension margin to prevent zero-division
    const latSpan = Math.max(maxLat - minLat, 0.0005);
    const lngSpan = Math.max(maxLng - minLng, 0.0005);

    const padding = 36;
    const width = 600;
    const viewHeight = height;

    const scaleX = (width - padding * 2) / lngSpan;
    const scaleY = (viewHeight - padding * 2) / latSpan;

    const toSvgCoords = (lat: number, lng: number) => {
      const x = padding + (lng - minLng) * scaleX;
      // Invert Y because SVG coordinates increase downwards
      const y = viewHeight - padding - (lat - minLat) * scaleY;
      return { x, y };
    };

    const svgCoords = allPoints.map((p) => toSvgCoords(p.lat, p.lng));

    let d = '';
    svgCoords.forEach((pt, index) => {
      if (index === 0) {
        d += `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
      } else {
        d += ` L ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
      }
    });

    return {
      pathData: d,
      startSvgPoint: svgCoords[0],
      endSvgPoint: svgCoords[svgCoords.length - 1],
      bounds: { minLat, maxLat, minLng, maxLng },
      hasPoints: true,
    };
  }, [allPoints, height]);

  if (!hasPoints) {
    return (
      <div
        style={{ height }}
        className={`relative w-full rounded-2xl bg-[#090b10] border border-white/[0.08] flex flex-col items-center justify-center text-slate-500 overflow-hidden ${className}`}
      >
        <div className="absolute inset-0 bg-[radial-gradient(#1f293d_1px,transparent_1px)] [background-size:16px_16px] opacity-40" />
        <Navigation className="w-8 h-8 text-slate-600 mb-2 animate-pulse" />
        <span className="text-xs font-mono uppercase tracking-wider text-slate-400">Awaiting Satellite Acquisition</span>
        <span className="text-[11px] text-slate-500 mt-1">Start recording to track your journey trajectory</span>
      </div>
    );
  }

  return (
    <div
      style={{ height }}
      className={`relative w-full rounded-2xl bg-[#090b10] border border-white/[0.08] overflow-hidden select-none ${className}`}
    >
      {/* Background Radar Grid */}
      <div className="absolute inset-0 bg-[radial-gradient(#1f293d_1px,transparent_1px)] [background-size:20px_20px] opacity-30" />
      <div className="absolute inset-0 bg-gradient-to-t from-[#090b10] via-transparent to-transparent pointer-events-none" />

      {/* SVG Canvas */}
      <svg
        viewBox={`0 0 600 ${height}`}
        className="w-full h-full relative z-10"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <linearGradient id="trajectoryGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#10b981" />
            <stop offset="50%" stopColor="#d4af37" />
            <stop offset="100%" stopColor="#f59e0b" />
          </linearGradient>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Path Glow Shadow */}
        {pathData && (
          <path
            d={pathData}
            fill="none"
            stroke="#d4af37"
            strokeWidth="6"
            strokeOpacity="0.25"
            strokeLinecap="round"
            strokeLinejoin="round"
            filter="url(#glow)"
          />
        )}

        {/* Primary Trajectory Path */}
        {pathData && (
          <path
            d={pathData}
            fill="none"
            stroke="url(#trajectoryGradient)"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {/* Start Point Marker (Emerald) */}
        {startSvgPoint && (
          <g transform={`translate(${startSvgPoint.x}, ${startSvgPoint.y})`}>
            <circle r="7" fill="#10b981" fillOpacity="0.3" />
            <circle r="4" fill="#10b981" stroke="#ffffff" strokeWidth="1.5" />
          </g>
        )}

        {/* Current Position Marker (Champagne Pulsing) */}
        {endSvgPoint && (
          <g transform={`translate(${endSvgPoint.x}, ${endSvgPoint.y})`}>
            <circle r="12" fill="#d4af37" fillOpacity="0.2" className="animate-ping" />
            <circle r="6" fill="#d4af37" stroke="#ffffff" strokeWidth="2" />
          </g>
        )}
      </svg>

      {/* Overlaid Telemetry Pill and Coordinates */}
      {showControls && (
        <div className="absolute top-3 left-3 z-20 flex items-center space-x-2">
          <div className="px-2.5 py-1 rounded-lg bg-black/75 backdrop-blur-md border border-white/10 text-[10px] font-mono text-emerald-400 flex items-center space-x-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>{allPoints.length} WAYPOINTS</span>
          </div>
          {currentLocation && (
            <div className="px-2.5 py-1 rounded-lg bg-black/75 backdrop-blur-md border border-white/10 text-[10px] font-mono text-slate-300">
              ACCURACY: &plusmn;{Math.round(currentLocation.accuracy)}m
            </div>
          )}
        </div>
      )}

      {/* Compass Indicator */}
      {showControls && (
        <div className="absolute top-3 right-3 z-20">
          <div className="w-8 h-8 rounded-full bg-black/75 backdrop-blur-md border border-white/10 flex items-center justify-center text-slate-400">
            <Compass className="w-4 h-4 text-amber-400" />
          </div>
        </div>
      )}

      {/* Trajectory Footnote */}
      <div className="absolute bottom-2.5 right-3 z-20 flex items-center space-x-2 text-[10px] font-mono text-slate-400 bg-black/60 px-2 py-0.5 rounded backdrop-blur-sm">
        <MapPin className="w-3 h-3 text-emerald-400" />
        <span>Vector Trail &bull; Offline Native</span>
      </div>
    </div>
  );
};
