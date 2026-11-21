/**
 * GPS Journeys & Offline Tracking View — AUREN Personal AI Command Center.
 * Dedicated feature view for recording journeys, inspecting offline synced records,
 * and managing field telemetry.
 */

import React, { useState } from 'react';
import { History, PlayCircle, Radio } from 'lucide-react';
import { JourneyRecorder } from './JourneyRecorder';
import { JourneyHistory } from './JourneyHistory';

export const JourneysView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'record' | 'history'>('record');
  const [refreshKey, setRefreshKey] = useState(0);

  const handleJourneySaved = () => {
    setRefreshKey((k) => k + 1);
    setActiveTab('history');
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div>
          <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-400 mb-1 uppercase tracking-wider">
            <Radio className="w-4 h-4 animate-pulse text-emerald-400" />
            <span>GPS Tracking &bull; Offline Persistent</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">GPS Journeys</h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            Track routes, record field assignments, and safely sync GPS telemetry offline.
          </p>
        </div>

        {/* View Switcher Tabs */}
        <div className="flex items-center p-1 rounded-xl bg-[#0e111a] border border-white/10">
          <button
            onClick={() => setActiveTab('record')}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
              activeTab === 'record'
                ? 'bg-amber-500 text-black font-semibold shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <PlayCircle className="w-3.5 h-3.5" />
            <span>Active Recorder</span>
          </button>

          <button
            onClick={() => setActiveTab('history')}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
              activeTab === 'history'
                ? 'bg-amber-500 text-black font-semibold shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <History className="w-3.5 h-3.5" />
            <span>Journey History</span>
          </button>
        </div>
      </div>

      {/* Main Tab Content */}
      {activeTab === 'record' ? (
        <div className="space-y-6">
          <JourneyRecorder onJourneySaved={handleJourneySaved} />
        </div>
      ) : (
        <div className="space-y-6" key={refreshKey}>
          <JourneyHistory />
        </div>
      )}
    </div>
  );
};
