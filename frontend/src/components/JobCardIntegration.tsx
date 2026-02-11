/**
 * JobCardIntegration Component - Work order creation from TechnicianChat
 *
 * Features:
 * - Create work orders from diagnosis results
 * - Display active work orders
 * - Priority selection and parts entry
 * - Integration with backend work order API
 */

import { useState, useEffect } from 'react';
import { FileText, Clock, AlertCircle, CheckCircle, Plus, X, Loader2 } from 'lucide-react';
import { authorizedFetch } from '../lib/api/client';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface TechnicianWorkOrder {
  id: string;
  site_id: string;
  equipment_id: string;
  fault_description: string;
  diagnosis: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  status: 'draft' | 'assigned' | 'in_progress' | 'complete';
  created_at: string;
  technician_notes?: string;
  parts_needed: string[];
  estimated_duration?: string;
}

interface JobCardProps {
  /** Diagnosis text from AI analysis */
  diagnosis: string;
  /** Fault code if identified */
  faultCode?: string;
  /** Equipment identifier */
  equipment?: string;
  /** Site ID for work order */
  siteId?: string;
  /** Callback when work order is created */
  onCreate?: (order: TechnicianWorkOrder) => void;
  /** Show compact mode */
  compact?: boolean;
}

export default function JobCardIntegration({
  diagnosis,
  faultCode,
  equipment,
  siteId = 'site-001',
  onCreate,
  compact = false,
}: JobCardProps) {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [priority, setPriority] = useState<'low' | 'medium' | 'high' | 'critical'>('medium');
  const [partsInput, setPartsInput] = useState('');
  const [notes, setNotes] = useState('');
  const [duration, setDuration] = useState('2-4 hours');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<TechnicianWorkOrder | null>(null);
  const [activeOrders, setActiveOrders] = useState<TechnicianWorkOrder[]>([]);
  const [loadingOrders, setLoadingOrders] = useState(false);

  // Load active work orders
  useEffect(() => {
    const fetchActiveOrders = async () => {
      setLoadingOrders(true);
      try {
        const response = await authorizedFetch(`${API_BASE_URL}/api/work-orders/technician?status=in_progress`);
        if (response.ok) {
          const orders = await response.json();
          setActiveOrders(orders.slice(0, 3)); // Show max 3
        }
      } catch (err) {
        console.error('Failed to fetch active orders:', err);
      } finally {
        setLoadingOrders(false);
      }
    };

    fetchActiveOrders();
  }, [success]); // Refresh when new order created

  const handleCreateWorkOrder = async () => {
    setIsSubmitting(true);
    setError(null);

    const workOrder = {
      site_id: siteId,
      equipment_id: equipment || 'unknown',
      fault_description: faultCode ? `${faultCode}: ${diagnosis}` : diagnosis,
      diagnosis: diagnosis,
      priority: priority,
      technician_notes: notes || undefined,
      parts_needed: partsInput
        ? partsInput.split(',').map((s) => s.trim()).filter(Boolean)
        : [],
      estimated_duration: duration || undefined,
    };

    try {
      const response = await authorizedFetch(`${API_BASE_URL}/api/work-orders/technician`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(workOrder),
      });

      if (response.ok) {
        const order = await response.json();
        setSuccess(order);
        setShowCreateForm(false);

        if (onCreate) {
          onCreate(order);
        }

        // Clear form
        setPartsInput('');
        setNotes('');
        setPriority('medium');
        setDuration('2-4 hours');

        // Auto-hide success after 5s
        setTimeout(() => setSuccess(null), 5000);
      } else {
        const data = await response.json();
        setError(data.detail || 'Failed to create work order');
      }
    } catch (err) {
      console.error('Failed to create work order:', err);
      setError('Network error - please try again');
    } finally {
      setIsSubmitting(false);
    }
  };

  const priorityColors = {
    low: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
    medium: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    critical: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  };

  const statusIcons = {
    draft: <FileText className="w-3 h-3" />,
    assigned: <AlertCircle className="w-3 h-3" />,
    in_progress: <Clock className="w-3 h-3" />,
    complete: <CheckCircle className="w-3 h-3" />,
  };

  // Success message
  if (success) {
    return (
      <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-green-800 dark:text-green-200">Work Order Created</p>
            <p className="text-sm text-green-700 dark:text-green-300 mt-1">
              ID: <span className="font-mono">{success.id}</span>
            </p>
            <p className="text-xs text-green-600 dark:text-green-400 mt-1">
              Status: {success.status} • Priority: {success.priority}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Create Work Order Button / Form */}
      {!showCreateForm ? (
        <button
          onClick={() => setShowCreateForm(true)}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-5 h-5" />
          <span>Create Work Order</span>
        </button>
      ) : (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="font-medium text-gray-900 dark:text-white">New Work Order</h4>
            <button
              onClick={() => setShowCreateForm(false)}
              className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
            >
              <X className="w-4 h-4 text-gray-500" />
            </button>
          </div>

          {/* Fault Description (read-only) */}
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Fault Description
            </label>
            <p className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded px-3 py-2">
              {faultCode && <span className="font-mono text-red-600 dark:text-red-400 mr-2">{faultCode}</span>}
              {diagnosis.slice(0, 150)}{diagnosis.length > 150 ? '...' : ''}
            </p>
          </div>

          {/* Priority */}
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Priority
            </label>
            <div className="flex gap-2">
              {(['low', 'medium', 'high', 'critical'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPriority(p)}
                  className={`px-3 py-1.5 rounded text-xs font-medium capitalize transition-colors ${
                    priority === p
                      ? priorityColors[p]
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Parts Needed */}
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Parts Needed (comma separated)
            </label>
            <input
              type="text"
              value={partsInput}
              onChange={(e) => setPartsInput(e.target.value)}
              placeholder="e.g., Oil Filter, Gaskets, Sensor"
              className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Duration */}
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Estimated Duration
            </label>
            <select
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="< 1 hour">Less than 1 hour</option>
              <option value="1-2 hours">1-2 hours</option>
              <option value="2-4 hours">2-4 hours</option>
              <option value="4-8 hours">Half day (4-8 hours)</option>
              <option value="1 day">Full day</option>
              <option value="2+ days">Multiple days</option>
            </select>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Additional Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any additional observations..."
              rows={2}
              className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2">
            <button
              onClick={handleCreateWorkOrder}
              disabled={isSubmitting}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <FileText className="w-4 h-4" />
                  Create Work Order
                </>
              )}
            </button>
            <button
              onClick={() => setShowCreateForm(false)}
              disabled={isSubmitting}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Active Work Orders (if not compact mode) */}
      {!compact && !showCreateForm && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">Your Active Work Orders</h4>

          {loadingOrders ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          ) : activeOrders.length > 0 ? (
            <div className="space-y-2">
              {activeOrders.map((order) => (
                <div
                  key={order.id}
                  className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm text-gray-900 dark:text-white truncate">
                        {order.equipment_id}
                      </p>
                      <p className="text-xs text-gray-600 dark:text-gray-400 truncate">
                        {order.fault_description.slice(0, 50)}...
                      </p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className={`text-xs px-2 py-0.5 rounded ${priorityColors[order.priority]}`}>
                          {order.priority}
                        </span>
                        <span className="text-xs text-gray-500">•</span>
                        <span className="text-xs text-gray-600 dark:text-gray-400 flex items-center gap-1">
                          {statusIcons[order.status]}
                          {order.status.replace('_', ' ')}
                        </span>
                      </div>
                    </div>
                    <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
                      <FileText className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
              No active work orders
            </p>
          )}
        </div>
      )}
    </div>
  );
}
