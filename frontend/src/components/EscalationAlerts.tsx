import React, { useState, useEffect } from 'react';
import { Card } from './Card';
import { Badge } from './Badge';
import { AlertTriangle, Bell, CheckCircle, X } from 'lucide-react';
import { api } from '@/lib/api';
import { PageLoading } from './PageLoading';

interface EscalationAlert {
  id: string;
  escalation_level: number;
  device_id: string;
  device_name: string;
  point_name: string;
  current_value: number;
  boundary_value: number;
  approach_percentage: number;
  timestamp: string;
  message: string;
  acknowledged: boolean;
}

interface EscalationAlertsProps {
  autoRefresh?: boolean;
  refreshInterval?: number;
  maxAlerts?: number;
}

export const EscalationAlerts: React.FC<EscalationAlertsProps> = ({
  autoRefresh = true,
  refreshInterval = 5000,
  maxAlerts = 5,
}) => {
  const [alerts, setAlerts] = useState<EscalationAlert[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showUrgentModal, setShowUrgentModal] = useState(false);
  const [urgentAlert, setUrgentAlert] = useState<EscalationAlert | null>(null);

  const fetchAlerts = async () => {
    setIsLoading(true);
    try {
      const response = await api.getEscalationAlerts();
      const alertsData = response.data || [];
      setAlerts(alertsData.slice(0, maxAlerts));

      // Check for Level 3+ alerts
      const criticalAlert = alertsData.find(
        (a: any) => a.escalation_level >= 3 && !a.acknowledged
      );
      if (criticalAlert) {
        setUrgentAlert(criticalAlert);
        setShowUrgentModal(true);
        playAlert();
      }
    } catch (error) {
      console.error('Failed to fetch escalation alerts:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
    if (autoRefresh) {
      const interval = setInterval(fetchAlerts, refreshInterval);
      return () => clearInterval(interval);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, refreshInterval]);

  const playAlert = () => {
    // Play sound notification for Level 3+ alerts
    try {
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);

      oscillator.frequency.value = 800;
      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);

      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.5);
    } catch (_error) {
      // Fallback: just log if audio context not available
      console.log('Alert triggered - audio not available');
    }
  };

  const acknowledgeAlert = async (alertId: string) => {
    try {
      await api.acknowledgeEscalation(alertId, 'operator', 'Acknowledged via dashboard');
      setAlerts((prev) =>
        prev.map((a) =>
          a.id === alertId ? { ...a, acknowledged: true } : a
        )
      );
      if (urgentAlert?.id === alertId) {
        setShowUrgentModal(false);
      }
    } catch (error) {
      console.error('Failed to acknowledge alert:', error);
    }
  };

  const getEscalationColor = (level: number) => {
    switch (level) {
      case 0:
        return 'bg-green-500';
      case 1:
        return 'bg-yellow-500';
      case 2:
        return 'bg-orange-500';
      case 3:
        return 'bg-red-500';
      case 4:
        return 'bg-purple-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getEscalationText = (level: number) => {
    switch (level) {
      case 0:
        return 'Safe';
      case 1:
        return 'Warning';
      case 2:
        return 'Alert';
      case 3:
        return 'Critical';
      case 4:
        return 'Emergency';
      default:
        return 'Unknown';
    }
  };

  return (
    <>
      <Card className="p-6 rounded-lg">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center space-x-2">
            <Bell className="h-5 w-5 text-gray-600" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Escalation Alerts
            </h3>
          </div>
          {alerts.length > 0 && (
            <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
              {alerts.length} Active
            </span>
          )}
        </div>

        {isLoading ? (
          <PageLoading compact message="Loading escalation alerts..." />
        ) : (
          <div className="space-y-3">
            {alerts.length === 0 ? (
              <div className="text-center py-8">
                <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-2" />
                <p className="text-gray-500">All systems within safe boundaries</p>
              </div>
            ) : (
              alerts.map((alert) => (
                <div
                  key={alert.id}
                  className={`border-l-4 p-3 rounded transition-colors ${
                    alert.acknowledged
                      ? 'border-l-gray-400 bg-gray-50 dark:bg-gray-800'
                      : getEscalationColor(alert.escalation_level).replace('bg-', 'border-l-')
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center space-x-2 flex-1">
                      <AlertTriangle
                        className={`h-4 w-4 flex-shrink-0 ${
                          alert.escalation_level >= 3
                            ? 'text-red-500'
                            : 'text-yellow-500'
                        }`}
                      />
                      <div>
                        <div className="font-medium text-gray-900 dark:text-gray-100">
                          {alert.device_name}
                        </div>
                        <div className="text-xs text-gray-500">
                          {alert.point_name}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Badge className={getEscalationColor(alert.escalation_level) + ' text-white'}>
                        {getEscalationText(alert.escalation_level)}
                      </Badge>
                      {!alert.acknowledged && (
                        <button
                          onClick={() => acknowledgeAlert(alert.id)}
                          className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors"
                          aria-label="Acknowledge"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="text-sm text-gray-600 dark:text-gray-400 ml-6 mb-2">
                    <span className="font-medium">Approach:</span> {alert.approach_percentage.toFixed(1)}%
                    {alert.current_value !== undefined && (
                      <>
                        {' • '}
                        <span className="font-medium">Current:</span> {alert.current_value.toFixed(2)}
                        {' / '}
                        <span className="font-medium">Boundary:</span> {alert.boundary_value.toFixed(2)}
                      </>
                    )}
                  </div>

                  <div className="text-xs text-gray-500 ml-6">
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </Card>

      {/* Urgent Alert Modal */}
      {showUrgentModal && urgentAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <Card className="w-96 p-6 rounded-lg shadow-md border-2 border-red-500">
            <div className="flex items-center space-x-3 mb-4">
              <AlertTriangle className="h-8 w-8 text-red-600 animate-pulse" />
              <h2 className="text-2xl font-bold text-red-600">URGENT ALERT</h2>
            </div>

            <div className="bg-red-50 dark:bg-red-900 p-4 rounded mb-4 border border-red-200">
              <div className="font-bold text-gray-900 dark:text-gray-100 mb-2">
                {urgentAlert.device_name}
              </div>
              <div className="text-sm text-gray-700 dark:text-gray-300 mb-3">
                {urgentAlert.message}
              </div>

              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="font-medium">Current:</span>{' '}
                  {urgentAlert.current_value.toFixed(2)}
                </div>
                <div>
                  <span className="font-medium">Boundary:</span>{' '}
                  {urgentAlert.boundary_value.toFixed(2)}
                </div>
                <div>
                  <span className="font-medium">Approach:</span>{' '}
                  {urgentAlert.approach_percentage.toFixed(1)}%
                </div>
                <div>
                  <span className="font-medium">Level:</span>{' '}
                  {getEscalationText(urgentAlert.escalation_level)}
                </div>
              </div>
            </div>

            <div className="flex space-x-3">
              <button
                onClick={() => acknowledgeAlert(urgentAlert.id)}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded font-medium hover:bg-blue-700 transition-colors"
              >
                Acknowledge
              </button>
              <button
                onClick={() => setShowUrgentModal(false)}
                className="flex-1 px-4 py-2 bg-gray-300 text-gray-900 rounded font-medium hover:bg-gray-400 transition-colors"
              >
                Dismiss
              </button>
            </div>
          </Card>
        </div>
      )}
    </>
  );
};
