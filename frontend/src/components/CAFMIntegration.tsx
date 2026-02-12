import { useState, useEffect } from 'react';
import { RefreshCw as Sync, AlertCircle, CheckCircle2, Settings } from 'lucide-react';

interface CAFMConfig {
  system: 'archibus' | 'planon' | 'maximo';
  api_url: string;
  username: string;
  sync_enabled: boolean;
  last_sync: string;
}

export default function CAFMIntegration() {
  const [config, setConfig] = useState<CAFMConfig | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCAFMConfig();
  }, []);

  const loadCAFMConfig = async () => {
    try {
      const response = await fetch('/api/cafm/config');
      if (response.ok) {
        const data = await response.json();
        setConfig(data);
      } else {
        // Default config if not found
        setConfig({
          system: 'archibus',
          api_url: '',
          username: '',
          sync_enabled: false,
          last_sync: ''
        });
      }
    } catch (error) {
      console.error('Failed to load CAFM config:', error);
      setConfig({
        system: 'archibus',
        api_url: '',
        username: '',
        sync_enabled: false,
        last_sync: ''
      });
    } finally {
      setLoading(false);
    }
  };

  const saveCAFMConfig = async (newConfig: CAFMConfig) => {
    try {
      const response = await fetch('/api/cafm/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig)
      });
      if (response.ok) {
        setConfig(newConfig);
        setSyncStatus('Configuration saved successfully');
        setTimeout(() => setSyncStatus(null), 3000);
      } else {
        setSyncStatus('Failed to save configuration');
      }
    } catch (error) {
      console.error('Failed to save config:', error);
      setSyncStatus('Failed to save configuration');
    }
  };

  const testConnection = async () => {
    setIsSyncing(true);
    setSyncStatus(null);
    try {
      const response = await fetch('/api/cafm/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json();
      setSyncStatus(data.success ? 'Connection successful!' : 'Connection failed');
    } catch (error) {
      console.error('Connection test error:', error);
      setSyncStatus('Connection failed');
    } finally {
      setIsSyncing(false);
    }
  };

  const syncNow = async () => {
    setIsSyncing(true);
    setSyncStatus(null);
    try {
      const response = await fetch('/api/cafm/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json();
      setSyncStatus(`Synced ${data.work_orders_synced || 0} work orders, ${data.assets_synced || 0} assets`);
    } catch (error) {
      console.error('Sync error:', error);
      setSyncStatus('Sync failed');
    } finally {
      setIsSyncing(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-gray-400">
        Loading CAFM configuration...
      </div>
    );
  }

  if (!config) {
    return (
      <div className="p-6 text-center text-red-600">
        Unable to load CAFM configuration
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Connection Status */}
      <div className="bg-white border rounded-lg p-4">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Settings className="w-5 h-5" />
          CAFM Connection
        </h3>

        <div className="flex items-center justify-between mb-4 p-3 bg-gray-50 rounded-lg">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-green-600" />
            <span className="text-sm font-medium">{config.system.toUpperCase()} Connected</span>
          </div>
          <button
            onClick={testConnection}
            disabled={isSyncing}
            className="px-3 py-1 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Test Connection
          </button>
        </div>

        {syncStatus && (
          <div className={`p-3 rounded-lg text-sm mb-4 ${
            syncStatus.includes('successful') || syncStatus.includes('Synced')
              ? 'bg-green-50 text-green-700 border border-green-200'
              : syncStatus.includes('saved')
                ? 'bg-blue-50 text-blue-700 border border-blue-200'
                : 'bg-red-50 text-red-700 border border-red-200'
          }`}>
            <div className="flex items-center gap-2">
              {syncStatus.includes('successful') || syncStatus.includes('Synced') ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : (
                <AlertCircle className="w-4 h-4" />
              )}
              {syncStatus}
            </div>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              CAFM System
            </label>
            <select
              value={config.system}
              onChange={(e) => saveCAFMConfig({...config, system: e.target.value as any})}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="archibus">Archibus</option>
              <option value="planon">Planon</option>
              <option value="maximo">Maximo</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              API URL
            </label>
            <input
              type="url"
              value={config.api_url}
              onChange={(e) => setConfig({...config, api_url: e.target.value})}
              onBlur={(e) => saveCAFMConfig({...config, api_url: e.target.value})}
              placeholder="https://cafm-system.example.com/api"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Username
            </label>
            <input
              type="text"
              value={config.username}
              onChange={(e) => setConfig({...config, username: e.target.value})}
              onBlur={(e) => saveCAFMConfig({...config, username: e.target.value})}
              placeholder="CAFM system username"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg">
            <input
              type="checkbox"
              id="sync-enabled"
              checked={config.sync_enabled}
              onChange={(e) => saveCAFMConfig({...config, sync_enabled: e.target.checked})}
              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
            />
            <label htmlFor="sync-enabled" className="text-sm text-gray-700 cursor-pointer">
              Enable automatic sync (every hour)
            </label>
          </div>

          {config.last_sync && (
            <div className="p-3 bg-gray-50 rounded-lg">
              <p className="text-xs text-gray-600">
                Last sync: {new Date(config.last_sync).toLocaleString()}
              </p>
            </div>
          )}

          <button
            onClick={syncNow}
            disabled={isSyncing || !config.sync_enabled}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2 font-medium"
          >
            <Sync className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} />
            {isSyncing ? 'Syncing...' : 'Sync Now'}
          </button>
        </div>
      </div>

      {/* Asset Sync Stats */}
      <div className="bg-white border rounded-lg p-4">
        <h3 className="text-lg font-semibold mb-4">Asset Sync Statistics</h3>

        <div className="grid grid-cols-3 gap-4">
          <StatBox label="Assets in CAFM" value="1,247" color="blue" />
          <StatBox label="Synced to SENTINEL" value="1,198" color="green" />
          <StatBox label="Need Review" value="49" color="orange" />
        </div>

        <div className="mt-4">
          <button className="w-full px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm font-medium text-gray-700">
            Review Unmatched Assets
          </button>
        </div>
      </div>

      {/* Work Order Sync Stats */}
      <div className="bg-white border rounded-lg p-4">
        <h3 className="text-lg font-semibold mb-4">Work Order Sync Statistics</h3>

        <div className="grid grid-cols-3 gap-4">
          <StatBox label="Work Orders in CAFM" value="342" color="purple" />
          <StatBox label="Synced to SENTINEL" value="338" color="green" />
          <StatBox label="Pending Push" value="4" color="orange" />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <button className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm font-medium text-gray-700">
            View Pending
          </button>
          <button className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm font-medium text-gray-700">
            Push All
          </button>
        </div>
      </div>

      {/* Integration Info */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-blue-900 mb-2">About CAFM Integration</h4>
        <p className="text-sm text-blue-800">
          This connector enables bidirectional synchronization between SENTINEL and your CAFM system.
          Work orders, assets, and maintenance schedules are automatically synced to keep both systems in sync.
        </p>
      </div>
    </div>
  );
}

function StatBox({ label, value, color }: { label: string; value: string; color: string }) {
  const colorClasses = {
    blue: 'text-blue-600',
    green: 'text-green-600',
    orange: 'text-orange-600',
    purple: 'text-purple-600'
  };

  return (
    <div className="text-center p-3 bg-gray-50 rounded-lg">
      <p className="text-xs text-gray-600 uppercase font-medium">{label}</p>
      <p className={`text-2xl font-bold ${colorClasses[color as keyof typeof colorClasses]}`}>
        {value}
      </p>
    </div>
  );
}
