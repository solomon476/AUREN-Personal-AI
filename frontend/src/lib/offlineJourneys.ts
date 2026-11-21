/**
 * AUREN Offline GPS Journey Storage & Resilient Sync Engine.
 * Implements persistent IndexedDB storage, GPS noise filtering (jitter/drift rejection),
 * distance calculation (Haversine formula), and automatic reconnection synchronization.
 */

import { GPSPoint, JourneyCreatePayload, journeysApi } from '../api/journeys';

export interface ActiveJourneyState {
  id: string;
  title: string;
  status: 'recording' | 'paused';
  startedAt: string;
  isTeamAssignment: boolean;
  assignmentSite?: string;
  assignmentPurpose?: string;
  assignmentNotes?: string;
  checkInTime?: string;
  checkInCoords?: string;
  points: GPSPoint[];
  distanceMeters: number;
  durationSeconds: number;
  avgSpeedKmh: number;
  idempotencyKey: string;
}

export interface OfflineJourneyRecord {
  id: string;
  payload: JourneyCreatePayload;
  syncStatus: 'pending' | 'synced' | 'failed';
  syncError?: string;
  updatedAt: string;
}

const DB_NAME = 'auren_journeys_db';
const DB_VERSION = 1;
const STORE_ACTIVE = 'active_journey';
const STORE_COMPLETED = 'offline_journeys';

function openJourneysDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined' || !window.indexedDB) {
      reject(new Error('IndexedDB not supported in current environment'));
      return;
    }
    const request = window.indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_ACTIVE)) {
        db.createObjectStore(STORE_ACTIVE, { keyPath: 'key' });
      }
      if (!db.objectStoreNames.contains(STORE_COMPLETED)) {
        db.createObjectStore(STORE_COMPLETED, { keyPath: 'id' });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Calculates great-circle distance between two GPS coordinates using Haversine formula in meters.
 */
export function calculateHaversineDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const R = 6371000; // Earth's radius in meters
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * Filters out inaccurate fixes and stationary GPS noise/drift.
 * Discards fixes with horizontal accuracy > 35m or movement < 3m when stationary.
 */
export function shouldAcceptGPSPoint(
  newPoint: GPSPoint,
  lastPoint: GPSPoint | null
): boolean {
  if (newPoint.accuracy > 35) {
    return false;
  }
  if (!lastPoint) {
    return true;
  }

  const dist = calculateHaversineDistance(
    lastPoint.lat,
    lastPoint.lng,
    newPoint.lat,
    newPoint.lng
  );

  // If distance is less than 3m and speed is low or absent, filter out stationary jitter
  if (dist < 3.0 && (newPoint.speed === null || newPoint.speed === undefined || newPoint.speed < 0.5)) {
    return false;
  }

  return true;
}

// Active Journey Persistence
export async function getActiveJourney(): Promise<ActiveJourneyState | null> {
  try {
    const db = await openJourneysDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_ACTIVE, 'readonly');
      const store = tx.objectStore(STORE_ACTIVE);
      const req = store.get('current');
      req.onsuccess = () => resolve(req.result ? req.result.data : null);
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

export async function saveActiveJourney(state: ActiveJourneyState): Promise<void> {
  try {
    const db = await openJourneysDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_ACTIVE, 'readwrite');
      const store = tx.objectStore(STORE_ACTIVE);
      const req = store.put({ key: 'current', data: state });
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn('Failed to save active journey to IndexedDB', err);
  }
}

export async function clearActiveJourney(): Promise<void> {
  try {
    const db = await openJourneysDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_ACTIVE, 'readwrite');
      const store = tx.objectStore(STORE_ACTIVE);
      const req = store.delete('current');
      req.onsuccess = () => resolve();
      req.onerror = () => resolve();
    });
  } catch {
    // Non-fatal
  }
}

// Completed Offline Journeys Store
export async function saveCompletedOfflineJourney(
  payload: JourneyCreatePayload
): Promise<void> {
  const id = payload.id || `local_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
  const record: OfflineJourneyRecord = {
    id,
    payload: { ...payload, id },
    syncStatus: 'pending',
    updatedAt: new Date().toISOString(),
  };

  try {
    const db = await openJourneysDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_COMPLETED, 'readwrite');
      const store = tx.objectStore(STORE_COMPLETED);
      const req = store.put(record);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch (err) {
    console.warn('Failed to save offline journey to IndexedDB', err);
  }
}

export async function getPendingOfflineJourneys(): Promise<OfflineJourneyRecord[]> {
  try {
    const all = await getAllOfflineJourneys();
    return all.filter((item) => item.syncStatus === 'pending' || item.syncStatus === 'failed');
  } catch {
    return [];
  }
}

export async function getAllOfflineJourneys(): Promise<OfflineJourneyRecord[]> {
  try {
    const db = await openJourneysDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_COMPLETED, 'readonly');
      const store = tx.objectStore(STORE_COMPLETED);
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => resolve([]);
    });
  } catch {
    return [];
  }
}

export async function markOfflineJourneySynced(id: string): Promise<void> {
  try {
    const db = await openJourneysDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_COMPLETED, 'readwrite');
      const store = tx.objectStore(STORE_COMPLETED);
      const getReq = store.get(id);
      getReq.onsuccess = () => {
        if (getReq.result) {
          const item = getReq.result;
          item.syncStatus = 'synced';
          item.syncError = undefined;
          item.updatedAt = new Date().toISOString();
          store.put(item);
        }
        resolve();
      };
      getReq.onerror = () => resolve();
    });
  } catch {
    // Non-fatal
  }
}

export async function markOfflineJourneyFailed(id: string, error: string): Promise<void> {
  try {
    const db = await openJourneysDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_COMPLETED, 'readwrite');
      const store = tx.objectStore(STORE_COMPLETED);
      const getReq = store.get(id);
      getReq.onsuccess = () => {
        if (getReq.result) {
          const item = getReq.result;
          item.syncStatus = 'failed';
          item.syncError = error;
          item.updatedAt = new Date().toISOString();
          store.put(item);
        }
        resolve();
      };
      getReq.onerror = () => resolve();
    });
  } catch {
    // Non-fatal
  }
}

// Synchronization Engine with Listener Support
type SyncListener = (status: {
  isSyncing: boolean;
  syncedCount: number;
  pendingCount: number;
  lastError?: string | null;
}) => void;

const listeners: Set<SyncListener> = new Set();
let isCurrentlySyncing = false;

export function subscribeToSyncUpdates(listener: SyncListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notifySync(data: {
  isSyncing: boolean;
  syncedCount: number;
  pendingCount: number;
  lastError?: string | null;
}) {
  listeners.forEach((fn) => {
    try {
      fn(data);
    } catch {
      // Ignore listener error
    }
  });
}

/**
 * Triggers batch synchronization of all unsynced completed journeys.
 */
export async function syncOfflineJourneys(): Promise<{
  synced: number;
  failed: number;
}> {
  if (isCurrentlySyncing) {
    return { synced: 0, failed: 0 };
  }
  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    return { synced: 0, failed: 0 };
  }

  isCurrentlySyncing = true;
  const pending = await getPendingOfflineJourneys();

  if (pending.length === 0) {
    isCurrentlySyncing = false;
    notifySync({ isSyncing: false, syncedCount: 0, pendingCount: 0 });
    return { synced: 0, failed: 0 };
  }

  notifySync({ isSyncing: true, syncedCount: 0, pendingCount: pending.length });

  let synced = 0;
  let failed = 0;
  let lastError: string | null = null;

  try {
    const payloads = pending.map((r) => r.payload);
    const response = await journeysApi.syncBatch({ journeys: payloads });

    for (const record of pending) {
      await markOfflineJourneySynced(record.id);
      synced++;
    }

    notifySync({
      isSyncing: false,
      syncedCount: response.synced_count || synced,
      pendingCount: 0,
    });
  } catch (err: unknown) {
    const errMsg = err instanceof Error ? err.message : 'Network sync failed';
    lastError = errMsg;
    for (const record of pending) {
      await markOfflineJourneyFailed(record.id, errMsg);
      failed++;
    }
    notifySync({
      isSyncing: false,
      syncedCount: 0,
      pendingCount: pending.length,
      lastError,
    });
  } finally {
    isCurrentlySyncing = false;
  }

  return { synced, failed };
}

// Auto-sync listener when browser reconnects to internet
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    console.info('AUREN online detected: triggering automatic journey sync...');
    syncOfflineJourneys();
  });
}

