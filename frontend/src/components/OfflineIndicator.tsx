/**
 * OfflineIndicator Component
 *
 * Shows connection status indicator when offline.
 * Uses browser online/offline events to detect network availability.
 */

import { useEffect, useState } from 'react';
import { WifiOff, RefreshCw } from 'lucide-react';
import { getSyncQueue } from '../lib/offlineStorage';

interface OfflineIndicatorProps {
  /** Show in compact mode */
  compact?: boolean;
}

export default function OfflineIndicator({ compact = false }: OfflineIndicatorProps) {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [pendingSyncs, setPendingSyncs] = useState(0);

  useEffect(() => {
    // Check initial state
    const queue = getSyncQueue();
    setPendingSyncs(queue.length);

    // Listen for online/offline events
    const handleOnline = () => {
      setIsOnline(true);
      // Auto-clear sync queue indicator after sync completes
      setTimeout(() => {
        const updatedQueue = getSyncQueue();
        setPendingSyncs(updatedQueue.length);
      }, 2000);
    };

    const handleOffline = () => {
      setIsOnline(false);
      const queue = getSyncQueue();
      setPendingSyncs(queue.length);
    };

    // Monitor for sync queue changes
    const syncCheckInterval = setInterval(() => {
      const queue = getSyncQueue();
      setPendingSyncs(queue.length);
    }, 5000);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      clearInterval(syncCheckInterval);
    };
  }, []);

  // Don't show if online and no pending syncs
  if (isOnline && pendingSyncs === 0) return null;

  if (compact) {
    return (
      <div className="flex items-center gap-1">
        {!isOnline && (
          <div className="flex items-center gap-1 px-2 py-1 text-xs rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
            <WifiOff className="w-3 h-3" />
            <span>Offline</span>
          </div>
        )}
        {pendingSyncs > 0 && (
          <div className="flex items-center gap-1 px-2 py-1 text-xs rounded bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400">
            <RefreshCw className="w-3 h-3 animate-spin" />
            <span>{pendingSyncs} pending</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="fixed bottom-20 left-1/2 transform -translate-x-1/2 z-50">
      {!isOnline && (
        <div className="bg-gray-900 text-white px-4 py-2 rounded-full shadow-lg flex items-center gap-2 animate-in fade-in slide-in-from-bottom-2">
          <WifiOff className="w-4 h-4 text-red-400" />
          <span className="text-sm font-medium">Offline</span>
          <span className="text-xs text-gray-400">Using cached data</span>
        </div>
      )}

      {isOnline && pendingSyncs > 0 && (
        <div className="bg-blue-600 text-white px-4 py-2 rounded-full shadow-lg flex items-center gap-2 animate-in fade-in slide-in-from-bottom-2">
          <RefreshCw className="w-4 h-4 animate-spin" />
          <span className="text-sm font-medium">Syncing</span>
          <span className="text-xs">{pendingSyncs} changes</span>
        </div>
      )}
    </div>
  );
}
