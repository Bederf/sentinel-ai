/**
 * Offline Storage Service
 *
 * Manages caching of fault codes, repair procedures, and work orders
 * for offline access. Uses IndexedDB for persistent local storage.
 */

const CACHE_VERSION = 1;
const DB_NAME = 'sentinel-bms-offline';
const STORES = {
  FAULT_CODES: 'fault_codes',
  PROCEDURES: 'repair_procedures',
  WORK_ORDERS: 'work_orders',
  EQUIPMENT: 'equipment',
} as const;

export interface OfflineData {
  faultCodes: Record<string, any>;
  repairProcedures: Record<string, any>;
  workOrders: Record<string, any>;
  equipment: Record<string, any>;
  lastSync: string;
  syncStatus: 'synced' | 'pending' | 'error';
}

let dbInstance: IDBDatabase | null = null;

/**
 * Initialize IndexedDB connection
 */
async function initializeDB(): Promise<IDBDatabase> {
  if (dbInstance) {
    return dbInstance;
  }

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, CACHE_VERSION);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      dbInstance = request.result;
      resolve(dbInstance);
    };

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;

      // Create object stores if they don't exist
      Object.values(STORES).forEach((store) => {
        if (!db.objectStoreNames.contains(store)) {
          db.createObjectStore(store, { keyPath: 'id' });
        }
      });
    };
  });
}

/**
 * Cache fault codes for offline access
 */
export async function cacheFaultCodes(faultCodes: Record<string, any>) {
  try {
    const db = await initializeDB();
    const transaction = db.transaction([STORES.FAULT_CODES], 'readwrite');
    const store = transaction.objectStore(STORES.FAULT_CODES);

    // Clear existing and add new
    await new Promise<void>((resolve, reject) => {
      const clearRequest = store.clear();
      clearRequest.onsuccess = () => {
        Object.entries(faultCodes).forEach(([code, data]) => {
          store.add({ id: code, ...data });
        });
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
      };
      clearRequest.onerror = () => reject(clearRequest.error);
    });
  } catch (error) {
    console.warn('Failed to cache fault codes:', error);
  }
}

/**
 * Cache repair procedures for offline access
 */
export async function cacheRepairProcedures(procedures: Record<string, any>) {
  try {
    const db = await initializeDB();
    const transaction = db.transaction([STORES.PROCEDURES], 'readwrite');
    const store = transaction.objectStore(STORES.PROCEDURES);

    await new Promise<void>((resolve, reject) => {
      const clearRequest = store.clear();
      clearRequest.onsuccess = () => {
        Object.entries(procedures).forEach(([code, data]) => {
          store.add({ id: code, ...data });
        });
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
      };
      clearRequest.onerror = () => reject(clearRequest.error);
    });
  } catch (error) {
    console.warn('Failed to cache repair procedures:', error);
  }
}

/**
 * Cache equipment data for offline access
 */
export async function cacheEquipment(equipment: Record<string, any>) {
  try {
    const db = await initializeDB();
    const transaction = db.transaction([STORES.EQUIPMENT], 'readwrite');
    const store = transaction.objectStore(STORES.EQUIPMENT);

    await new Promise<void>((resolve, reject) => {
      const clearRequest = store.clear();
      clearRequest.onsuccess = () => {
        Object.entries(equipment).forEach(([id, data]) => {
          store.add({ id, ...data });
        });
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
      };
      clearRequest.onerror = () => reject(clearRequest.error);
    });
  } catch (error) {
    console.warn('Failed to cache equipment data:', error);
  }
}

/**
 * Get cached fault codes
 */
export async function getCachedFaultCodes(): Promise<Record<string, any>> {
  try {
    const db = await initializeDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction([STORES.FAULT_CODES], 'readonly');
      const store = transaction.objectStore(STORES.FAULT_CODES);
      const request = store.getAll();

      request.onsuccess = () => {
        const codes: Record<string, any> = {};
        request.result.forEach((item) => {
          const { id, ...rest } = item;
          codes[id] = rest;
        });
        resolve(codes);
      };
      request.onerror = () => reject(request.error);
    });
  } catch (error) {
    console.warn('Failed to get cached fault codes:', error);
    return {};
  }
}

/**
 * Get cached repair procedures
 */
export async function getCachedRepairProcedures(): Promise<Record<string, any>> {
  try {
    const db = await initializeDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction([STORES.PROCEDURES], 'readonly');
      const store = transaction.objectStore(STORES.PROCEDURES);
      const request = store.getAll();

      request.onsuccess = () => {
        const procedures: Record<string, any> = {};
        request.result.forEach((item) => {
          const { id, ...rest } = item;
          procedures[id] = rest;
        });
        resolve(procedures);
      };
      request.onerror = () => reject(request.error);
    });
  } catch (error) {
    console.warn('Failed to get cached repair procedures:', error);
    return {};
  }
}

/**
 * Get cached equipment
 */
export async function getCachedEquipment(): Promise<Record<string, any>> {
  try {
    const db = await initializeDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction([STORES.EQUIPMENT], 'readonly');
      const store = transaction.objectStore(STORES.EQUIPMENT);
      const request = store.getAll();

      request.onsuccess = () => {
        const equipment: Record<string, any> = {};
        request.result.forEach((item) => {
          const { id, ...rest } = item;
          equipment[id] = rest;
        });
        resolve(equipment);
      };
      request.onerror = () => reject(request.error);
    });
  } catch (error) {
    console.warn('Failed to get cached equipment:', error);
    return {};
  }
}

/**
 * Save work order for offline access
 */
export async function saveWorkOrderOffline(workOrder: any) {
  try {
    const db = await initializeDB();
    const transaction = db.transaction([STORES.WORK_ORDERS], 'readwrite');
    const store = transaction.objectStore(STORES.WORK_ORDERS);

    return new Promise<void>((resolve, reject) => {
      const request = store.put({ id: workOrder.id, ...workOrder });
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  } catch (error) {
    console.warn('Failed to save work order offline:', error);
  }
}

/**
 * Get offline work orders
 */
export async function getOfflineWorkOrders(): Promise<any[]> {
  try {
    const db = await initializeDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction([STORES.WORK_ORDERS], 'readonly');
      const store = transaction.objectStore(STORES.WORK_ORDERS);
      const request = store.getAll();

      request.onsuccess = () => {
        resolve(request.result);
      };
      request.onerror = () => reject(request.error);
    });
  } catch (error) {
    console.warn('Failed to get offline work orders:', error);
    return [];
  }
}

/**
 * Check if online
 */
export function isOnline(): boolean {
  return navigator.onLine;
}

/**
 * Get offline data summary
 */
export async function getOfflineSummary(): Promise<OfflineData> {
  const faultCodes = await getCachedFaultCodes();
  const repairProcedures = await getCachedRepairProcedures();
  const workOrders = await getOfflineWorkOrders();
  const equipment = await getCachedEquipment();

  return {
    faultCodes,
    repairProcedures,
    workOrders: workOrders.reduce((acc, wo) => {
      acc[wo.id] = wo;
      return acc;
    }, {} as Record<string, any>),
    equipment,
    lastSync: new Date().toISOString(),
    syncStatus: isOnline() ? 'synced' : 'pending',
  };
}

/**
 * Clear all offline data
 */
export async function clearOfflineData() {
  try {
    const db = await initializeDB();
    const transaction = db.transaction(Object.values(STORES), 'readwrite');

    Object.values(STORES).forEach((store) => {
      transaction.objectStore(store).clear();
    });

    return new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
  } catch (error) {
    console.warn('Failed to clear offline data:', error);
  }
}

/**
 * Set up online/offline event listeners
 */
export function setupOfflineListeners(
  onOnline?: () => void,
  onOffline?: () => void
) {
  window.addEventListener('online', () => {
    onOnline?.();
  });

  window.addEventListener('offline', () => {
    onOffline?.();
  });

  // Return cleanup function
  return () => {
    window.removeEventListener('online', onOnline ?? (() => {}));
    window.removeEventListener('offline', onOffline ?? (() => {}));
  };
}

/**
 * Queue operation for sync when online
 */
const syncQueue: Array<{ type: string; data: any }> = [];

export function queueForSync(type: string, data: any) {
  syncQueue.push({ type, data });
  localStorage.setItem('sentinel-sync-queue', JSON.stringify(syncQueue));
}

export function getSyncQueue() {
  try {
    const queued = localStorage.getItem('sentinel-sync-queue');
    return queued ? JSON.parse(queued) : [];
  } catch {
    return [];
  }
}

export function clearSyncQueue() {
  syncQueue.length = 0;
  localStorage.removeItem('sentinel-sync-queue');
}
