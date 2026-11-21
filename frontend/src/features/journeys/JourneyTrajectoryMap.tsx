/**
 * Interactive World Map & Offline Vector Trajectory for AUREN GPS Journeys.
 *
 * Capabilities:
 * - Real World Map: Interactive OpenStreetMap / CartoDB Street tiles & Esri Satellite imagery.
 * - Offline Resilient: Graceful one-click fallback to 2D vector radar trail when offline.
 * - Live GPS Telemetry: Polyline route tracking, start marker, live pulsing current fix,
 *   and satellite precision accuracy rings.
 * - Mobile Touch Responsive: Pinch to zoom, drag to pan, auto-center, and route bounding.
 */

import React, { useEffect, useRef, useState, useMemo } from 'react';
import { GPSPoint } from '../../api/journeys';
import {
  Compass,
  MapPin,
  Navigation,
  Layers,
  Crosshair,
  Maximize2,
  ZoomIn,
  ZoomOut,
  Radio,
  Globe,
} from 'lucide-react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export type MapMode = 'streets' | 'satellite' | 'radar';

interface JourneyTrajectoryMapProps {
  points: GPSPoint[];
  currentLocation?: GPSPoint | null;
  height?: number;
  className?: string;
  showControls?: boolean;
  initialMode?: MapMode;
}

const TILE_SERVERS = {
  streets: {
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    attribution: '&copy; <a href="https://carto.com/">CARTO</a> &bull; &copy; OpenStreetMap',
    maxZoom: 19,
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri, USGS, NOAA',
    maxZoom: 18,
  },
};

export const JourneyTrajectoryMap: React.FC<JourneyTrajectoryMapProps> = ({
  points,
  currentLocation,
  height = 320,
  className = '',
  showControls = true,
  initialMode = 'streets',
}) => {
  const [mapMode, setMapMode] = useState<MapMode>(initialMode);
  const [isMapReady, setIsMapReady] = useState(false);
  const [tileError, setTileError] = useState(false);

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const polylineRef = useRef<L.Polyline | null>(null);
  const startMarkerRef = useRef<L.Marker | null>(null);
  const currentMarkerRef = useRef<L.Marker | null>(null);
  const accuracyCircleRef = useRef<L.Circle | null>(null);
  const hasAutoCenteredRef = useRef(false);

  // Combine recorded points with current fix for calculations
  const allPoints = useMemo(() => {
    if (!currentLocation) return points;
    if (points.length === 0) return [currentLocation];
    return points;
  }, [points, currentLocation]);

  // Determine initial center and zoom
  const centerCoords = useMemo<[number, number]>(() => {
    if (currentLocation) return [currentLocation.lat, currentLocation.lng];
    if (points.length > 0) return [points[points.length - 1].lat, points[points.length - 1].lng];
    return [0, 20]; // Default global view
  }, [currentLocation, points]);

  // -------------------------------------------------------------------------
  // 1. Initialize Leaflet Map Instance
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!mapContainerRef.current || mapMode === 'radar') return;

    try {
      if (!mapInstanceRef.current) {
        const initialZoom = points.length > 0 || currentLocation ? 16 : 3;
        const map = L.map(mapContainerRef.current, {
          center: centerCoords,
          zoom: initialZoom,
          zoomControl: false,
          attributionControl: false,
        });

        // Add attribution cleanly at bottom right
        L.control
          .attribution({ position: 'bottomright', prefix: false })
          .addTo(map);

        mapInstanceRef.current = map;
        setIsMapReady(true);
      }
    } catch (err) {
      console.warn('[AUREN Map] Leaflet init error (falling back to radar):', err);
      setMapMode('radar');
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
        tileLayerRef.current = null;
        polylineRef.current = null;
        startMarkerRef.current = null;
        currentMarkerRef.current = null;
        accuracyCircleRef.current = null;
        setIsMapReady(false);
      }
    };
  }, [mapMode]);

  // -------------------------------------------------------------------------
  // 2. Handle Tile Layer Switching (Streets vs Satellite)
  // -------------------------------------------------------------------------
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapMode === 'radar') return;

    try {
      if (tileLayerRef.current) {
        map.removeLayer(tileLayerRef.current);
      }

      const config = TILE_SERVERS[mapMode];
      if (config) {
        const layer = L.tileLayer(config.url, {
          attribution: config.attribution,
          maxZoom: config.maxZoom,
          subdomains: mapMode === 'streets' ? 'abcd' : '',
        });

        layer.on('tileerror', () => {
          setTileError(true);
        });

        layer.addTo(map);
        tileLayerRef.current = layer;
        setTileError(false);
      }
    } catch (err) {
      console.warn('[AUREN Map] Tile layer error:', err);
    }
  }, [mapMode, isMapReady]);

  // -------------------------------------------------------------------------
  // 3. Update Markers, Accuracy Circle, and Polyline
  // -------------------------------------------------------------------------
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapMode === 'radar' || !isMapReady) return;

    try {
      const latLngs: L.LatLngExpression[] = allPoints.map((p) => [p.lat, p.lng]);

      // Route Polyline
      if (latLngs.length > 0) {
        if (!polylineRef.current) {
          polylineRef.current = L.polyline(latLngs, {
            color: '#059669', // Emerald 600
            weight: 4.5,
            opacity: 0.9,
            lineJoin: 'round',
            lineCap: 'round',
          }).addTo(map);
        } else {
          polylineRef.current.setLatLngs(latLngs);
        }
      }

      // Start Marker
      if (allPoints.length > 0) {
        const startPoint = allPoints[0];
        const startLatLng: [number, number] = [startPoint.lat, startPoint.lng];

        if (!startMarkerRef.current) {
          const startIcon = L.divIcon({
            className: 'auren-start-marker',
            html: `
              <div style="
                width: 18px;
                height: 18px;
                border-radius: 50%;
                background: #059669;
                border: 3px solid #ffffff;
                box-shadow: 0 2px 8px rgba(0,0,0,0.4);
                display: flex;
                align-items: center;
                justify-content: center;
              ">
                <div style="width: 4px; height: 4px; border-radius: 50%; background: #ffffff;"></div>
              </div>
            `,
            iconSize: [18, 18],
            iconAnchor: [9, 9],
          });

          startMarkerRef.current = L.marker(startLatLng, { icon: startIcon, title: 'Journey Origin' })
            .bindTooltip('Journey Start', { direction: 'top', offset: [0, -10] })
            .addTo(map);
        } else {
          startMarkerRef.current.setLatLng(startLatLng);
        }
      }

      // Current Location Fix & Accuracy Ring
      if (currentLocation) {
        const currLatLng: [number, number] = [currentLocation.lat, currentLocation.lng];

        // Accuracy Circle
        if (currentLocation.accuracy && currentLocation.accuracy > 0) {
          if (!accuracyCircleRef.current) {
            accuracyCircleRef.current = L.circle(currLatLng, {
              radius: Math.min(currentLocation.accuracy, 300),
              color: '#059669',
              fillColor: '#10b981',
              fillOpacity: 0.12,
              weight: 1.5,
              dashArray: '4, 4',
            }).addTo(map);
          } else {
            accuracyCircleRef.current.setLatLng(currLatLng);
            accuracyCircleRef.current.setRadius(Math.min(currentLocation.accuracy, 300));
          }
        }

        // Live Pulsing Beacon Marker
        if (!currentMarkerRef.current) {
          const currentIcon = L.divIcon({
            className: 'auren-current-beacon',
            html: `
              <div style="position: relative; width: 26px; height: 26px; display: flex; align-items: center; justify-content: center;">
                <div style="position: absolute; width: 26px; height: 26px; border-radius: 50%; background: rgba(16, 185, 129, 0.4); animation: auren-ping 1.6s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
                <div style="position: relative; width: 14px; height: 14px; border-radius: 50%; background: #047857; border: 2.5px solid #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.5);"></div>
              </div>
              <style>
                @keyframes auren-ping {
                  75%, 100% { transform: scale(2.2); opacity: 0; }
                }
              </style>
            `,
            iconSize: [26, 26],
            iconAnchor: [13, 13],
          });

          currentMarkerRef.current = L.marker(currLatLng, { icon: currentIcon, title: 'Current GPS Position' })
            .bindTooltip(`Live Location (&plusmn;${Math.round(currentLocation.accuracy)}m)`, { direction: 'top', offset: [0, -14] })
            .addTo(map);
        } else {
          currentMarkerRef.current.setLatLng(currLatLng);
        }

        // Auto center on initial load if not previously centered
        if (!hasAutoCenteredRef.current) {
          map.setView(currLatLng, Math.max(map.getZoom(), 16), { animate: true });
          hasAutoCenteredRef.current = true;
        }
      }
    } catch (err) {
      console.warn('[AUREN Map] Marker update warning:', err);
    }
  }, [allPoints, currentLocation, isMapReady, mapMode]);

  // Center on current location
  const handleCenterOnMe = () => {
    const map = mapInstanceRef.current;
    if (!map || !currentLocation) return;
    map.setView([currentLocation.lat, currentLocation.lng], 17, { animate: true });
  };

  // Fit all journey waypoints within view
  const handleFitBounds = () => {
    const map = mapInstanceRef.current;
    if (!map || allPoints.length === 0) return;
    const latLngs: L.LatLngExpression[] = allPoints.map((p) => [p.lat, p.lng]);
    const bounds = L.latLngBounds(latLngs);
    map.fitBounds(bounds, { padding: [35, 35], maxZoom: 18, animate: true });
  };

  const handleZoomIn = () => {
    mapInstanceRef.current?.zoomIn();
  };

  const handleZoomOut = () => {
    mapInstanceRef.current?.zoomOut();
  };

  // -------------------------------------------------------------------------
  // 4. SVG Offline Radar Calculations (Fallback / Mode)
  // -------------------------------------------------------------------------
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

    const latSpan = Math.max(maxLat - minLat, 0.0005);
    const lngSpan = Math.max(maxLng - minLng, 0.0005);

    const padding = 36;
    const width = 600;
    const viewHeight = height;

    const scaleX = (width - padding * 2) / lngSpan;
    const scaleY = (viewHeight - padding * 2) / latSpan;

    const toSvgCoords = (lat: number, lng: number) => {
      const x = padding + (lng - minLng) * scaleX;
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
      hasPoints: true,
    };
  }, [allPoints, height]);

  return (
    <div
      style={{ height }}
      className={`relative w-full rounded-2xl border border-slate-200/90 shadow-sm overflow-hidden select-none bg-slate-100 ${className}`}
    >
      {/* =================================================================== */}
      {/* Leaflet Real World Map Container */}
      {/* =================================================================== */}
      {mapMode !== 'radar' && (
        <div
          ref={mapContainerRef}
          style={{ height: '100%', width: '100%' }}
          className="relative z-0"
        />
      )}

      {/* =================================================================== */}
      {/* Offline Vector Radar Canvas (When mode === 'radar' or fallback)     */}
      {/* =================================================================== */}
      {mapMode === 'radar' && (
        <div className="absolute inset-0 bg-[#090b10] flex flex-col justify-between overflow-hidden">
          {/* Radar Grid Texture */}
          <div className="absolute inset-0 bg-[radial-gradient(#1f293d_1px,transparent_1px)] [background-size:20px_20px] opacity-30" />
          <div className="absolute inset-0 bg-gradient-to-t from-[#090b10] via-transparent to-transparent pointer-events-none" />

          {hasPoints ? (
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

              {startSvgPoint && (
                <g transform={`translate(${startSvgPoint.x}, ${startSvgPoint.y})`}>
                  <circle r="7" fill="#10b981" fillOpacity="0.3" />
                  <circle r="4" fill="#10b981" stroke="#ffffff" strokeWidth="1.5" />
                </g>
              )}

              {endSvgPoint && (
                <g transform={`translate(${endSvgPoint.x}, ${endSvgPoint.y})`}>
                  <circle r="12" fill="#d4af37" fillOpacity="0.2" className="animate-ping" />
                  <circle r="6" fill="#d4af37" stroke="#ffffff" strokeWidth="2" />
                </g>
              )}
            </svg>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 z-10 p-4 text-center">
              <Navigation className="w-8 h-8 text-slate-600 mb-2 animate-pulse" />
              <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
                Awaiting Satellite Acquisition
              </span>
              <span className="text-[11px] text-slate-500 mt-1">
                Start recording to track your journey trajectory
              </span>
            </div>
          )}
        </div>
      )}

      {/* =================================================================== */}
      {/* Floating Controls HUD: Mode Switcher & Telemetry                   */}
      {/* =================================================================== */}
      {showControls && (
        <>
          {/* Top-Left: Mode Switcher (Streets, Satellite, Radar) */}
          <div className="absolute top-3 left-3 z-[400] flex items-center space-x-1.5 p-1 bg-white/95 backdrop-blur-md rounded-xl border border-slate-200/90 shadow-sm">
            <button
              type="button"
              onClick={() => setMapMode('streets')}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold flex items-center space-x-1 transition cursor-pointer ${
                mapMode === 'streets'
                  ? 'bg-emerald-600 text-white shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
              title="Interactive Street Map"
            >
              <Globe className="w-3.5 h-3.5" />
              <span>Map</span>
            </button>

            <button
              type="button"
              onClick={() => setMapMode('satellite')}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold flex items-center space-x-1 transition cursor-pointer ${
                mapMode === 'satellite'
                  ? 'bg-emerald-600 text-white shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
              title="High-Resolution Satellite Imagery"
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Satellite</span>
            </button>

            <button
              type="button"
              onClick={() => setMapMode('radar')}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold flex items-center space-x-1 transition cursor-pointer ${
                mapMode === 'radar'
                  ? 'bg-slate-900 text-amber-300 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
              title="Offline Vector Radar Trail"
            >
              <Radio className="w-3.5 h-3.5" />
              <span>Radar</span>
            </button>
          </div>

          {/* Top-Right: Map Positioning & Zoom Tools */}
          <div className="absolute top-3 right-3 z-[400] flex flex-col space-y-1.5">
            {mapMode !== 'radar' && (
              <>
                <button
                  type="button"
                  onClick={handleCenterOnMe}
                  disabled={!currentLocation}
                  className="w-8 h-8 rounded-xl bg-white/95 backdrop-blur-md border border-slate-200/90 shadow-sm flex items-center justify-center text-slate-700 hover:text-emerald-600 hover:bg-white transition cursor-pointer disabled:opacity-40"
                  title="Center on my location"
                  aria-label="Center on my location"
                >
                  <Crosshair className="w-4 h-4 text-emerald-600" />
                </button>

                <button
                  type="button"
                  onClick={handleFitBounds}
                  disabled={allPoints.length === 0}
                  className="w-8 h-8 rounded-xl bg-white/95 backdrop-blur-md border border-slate-200/90 shadow-sm flex items-center justify-center text-slate-700 hover:text-emerald-600 hover:bg-white transition cursor-pointer disabled:opacity-40"
                  title="Fit entire journey route"
                  aria-label="Fit entire journey route"
                >
                  <Maximize2 className="w-4 h-4" />
                </button>

                <div className="flex flex-col bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-xl shadow-sm overflow-hidden">
                  <button
                    type="button"
                    onClick={handleZoomIn}
                    className="w-8 h-8 flex items-center justify-center text-slate-700 hover:text-emerald-600 hover:bg-slate-50 transition border-b border-slate-100 cursor-pointer"
                    title="Zoom in"
                    aria-label="Zoom in"
                  >
                    <ZoomIn className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={handleZoomOut}
                    className="w-8 h-8 flex items-center justify-center text-slate-700 hover:text-emerald-600 hover:bg-slate-50 transition cursor-pointer"
                    title="Zoom out"
                    aria-label="Zoom out"
                  >
                    <ZoomOut className="w-3.5 h-3.5" />
                  </button>
                </div>
              </>
            )}

            {mapMode === 'radar' && (
              <div className="w-8 h-8 rounded-xl bg-black/70 backdrop-blur-md border border-white/10 flex items-center justify-center text-amber-400">
                <Compass className="w-4 h-4" />
              </div>
            )}
          </div>

          {/* Bottom-Left: Live GPS Telemetry Pill */}
          <div className="absolute bottom-3 left-3 z-[400] flex items-center space-x-1.5 flex-wrap gap-y-1">
            <div className="px-2.5 py-1 rounded-lg bg-white/95 backdrop-blur-md border border-slate-200/90 text-[10px] font-mono text-emerald-700 font-bold flex items-center space-x-1.5 shadow-xs">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span>{allPoints.length} WAYPOINTS</span>
            </div>

            {currentLocation && (
              <div className="px-2.5 py-1 rounded-lg bg-white/95 backdrop-blur-md border border-slate-200/90 text-[10px] font-mono text-slate-700 shadow-xs">
                &plusmn;{Math.round(currentLocation.accuracy)}m GPS ACCURACY
              </div>
            )}

            {tileError && (
              <div className="px-2 py-0.5 rounded-lg bg-amber-50 border border-amber-200 text-[10px] text-amber-800 font-medium shadow-xs">
                Offline Tiles &bull; Radar Available
              </div>
            )}
          </div>

          {/* Bottom-Right: Active Layer Footnote */}
          <div className="absolute bottom-3 right-3 z-[400] hidden xs:flex items-center space-x-1.5 px-2 py-0.5 rounded-lg bg-white/90 backdrop-blur-sm border border-slate-200/80 text-[10px] font-mono text-slate-600 shadow-2xs">
            <MapPin className="w-3 h-3 text-emerald-600" />
            <span className="capitalize">{mapMode === 'radar' ? 'Vector Radar (Offline)' : `${mapMode} Map`}</span>
          </div>
        </>
      )}
    </div>
  );
};
