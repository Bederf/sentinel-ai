import { useState, useEffect } from 'react';
import { Package, Truck, CheckCircle, Clock, AlertCircle } from 'lucide-react';

interface TrackingInfo {
  order_reference: string;
  status: 'ordered' | 'shipped' | 'delivered' | 'cancelled';
  tracking_number?: string;
  estimated_delivery?: string;
  supplier: string;
  items: Array<{ name: string; qty: number }>;
}

interface OrderTrackingProps {
  orderId: string;
}

export default function OrderTracking({ orderId }: OrderTrackingProps) {
  const [tracking, setTracking] = useState<TrackingInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTracking();
  }, [orderId]);

  const fetchTracking = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/parts-orders/${orderId}/tracking`);
      if (!response.ok) {
        throw new Error('Failed to load tracking information');
      }
      const data = await response.json();
      setTracking(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tracking info');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white border rounded-lg p-4">
        <div className="flex items-center gap-2 text-gray-500">
          <Clock className="w-5 h-5 animate-spin" />
          Loading tracking information...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white border border-red-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-1" />
          <div>
            <p className="font-medium text-red-900">Error loading tracking</p>
            <p className="text-sm text-red-700">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!tracking) {
    return (
      <div className="bg-white border rounded-lg p-4">
        <p className="text-gray-500">No tracking information available</p>
      </div>
    );
  }

  const statusConfig = {
    ordered: {
      label: 'Order Placed',
      color: 'bg-blue-100 text-blue-700',
      icon: Package,
      description: 'Your order has been placed and is being prepared'
    },
    shipped: {
      label: 'Shipped',
      color: 'bg-yellow-100 text-yellow-700',
      icon: Truck,
      description: 'Your order is on its way'
    },
    delivered: {
      label: 'Delivered',
      color: 'bg-green-100 text-green-700',
      icon: CheckCircle,
      description: 'Your order has been delivered'
    },
    cancelled: {
      label: 'Cancelled',
      color: 'bg-red-100 text-red-700',
      icon: AlertCircle,
      description: 'This order has been cancelled'
    }
  };

  const config = statusConfig[tracking.status];
  const StatusIcon = config.icon;

  // Timeline steps
  const timelineSteps = [
    { status: 'ordered', label: 'Ordered', completed: ['ordered', 'shipped', 'delivered'] },
    { status: 'shipped', label: 'Shipped', completed: ['shipped', 'delivered'] },
    { status: 'delivered', label: 'Delivered', completed: ['delivered'] }
  ];

  return (
    <div className="bg-white border rounded-lg p-4">
      <h3 className="text-lg font-semibold mb-4">Order Tracking</h3>

      {/* Status Badge */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-3">
          <div className={`p-2 rounded-full ${config.color}`}>
            <StatusIcon className="w-6 h-6" />
          </div>
          <div>
            <p className={`inline-block px-3 py-1 rounded-full text-sm font-medium ${config.color}`}>
              {config.label}
            </p>
            <p className="text-sm text-gray-600 mt-1">{config.description}</p>
          </div>
        </div>
      </div>

      {/* Order Details */}
      <div className="bg-gray-50 rounded p-3 mb-6 space-y-2">
        <p className="text-sm">
          <span className="text-gray-600">Reference:</span>
          <span className="font-medium ml-2">{tracking.order_reference}</span>
        </p>
        <p className="text-sm">
          <span className="text-gray-600">Supplier:</span>
          <span className="font-medium ml-2">{tracking.supplier}</span>
        </p>
        {tracking.tracking_number && (
          <p className="text-sm">
            <span className="text-gray-600">Tracking:</span>
            <span className="font-medium ml-2">{tracking.tracking_number}</span>
          </p>
        )}
      </div>

      {/* Timeline */}
      <div className="mb-6">
        <p className="text-sm font-medium text-gray-700 mb-3">Delivery Timeline</p>
        <div className="space-y-2">
          {timelineSteps.map((step, idx) => {
            const isCompleted = step.completed.includes(tracking.status);
            const isCurrent = step.status === tracking.status;

            return (
              <div key={step.status} className="flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full ${
                  isCompleted ? 'bg-green-600' : isCurrent ? 'bg-blue-600' : 'bg-gray-300'
                }`} />
                <span className={`text-sm ${
                  isCompleted || isCurrent ? 'text-gray-900 font-medium' : 'text-gray-500'
                }`}>
                  {step.label}
                </span>
                {isCurrent && (
                  <Clock className="w-4 h-4 text-blue-600 ml-auto" />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Estimated Delivery */}
      {tracking.estimated_delivery && (
        <div className="bg-blue-50 border border-blue-200 rounded p-3 mb-6">
          <p className="text-sm font-medium text-blue-900">Estimated Delivery</p>
          <p className="text-sm text-blue-700">{tracking.estimated_delivery}</p>
        </div>
      )}

      {/* Items List */}
      <div>
        <p className="text-sm font-medium text-gray-700 mb-2">Items in Order</p>
        <ul className="space-y-1">
          {tracking.items.map((item, idx) => (
            <li key={idx} className="text-sm text-gray-600">
              <span className="font-medium">{item.qty}x</span> {item.name}
            </li>
          ))}
        </ul>
      </div>

      {/* Refresh Button */}
      <button
        onClick={fetchTracking}
        className="mt-4 w-full py-2 text-sm text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded transition-colors"
      >
        Refresh Tracking Information
      </button>
    </div>
  );
}
