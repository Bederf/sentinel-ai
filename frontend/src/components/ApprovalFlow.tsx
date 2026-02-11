import { CheckCircle, XCircle, AlertCircle } from 'lucide-react';

interface OrderItem {
  part_name: string;
  part_number: string;
  quantity: number;
  supplier: string;
  unit_price: string;
}

interface PendingOrder {
  id: string;
  technician_id: string;
  created_at: string;
  total_amount: string;
  items: OrderItem[];
  site_id: string;
}

interface ApprovalFlowProps {
  orders: PendingOrder[];
  onApprove: (orderId: string) => void;
  onReject: (orderId: string) => void;
  loading?: boolean;
}

export default function ApprovalFlow({ orders, onApprove, onReject, loading = false }: ApprovalFlowProps) {
  if (orders.length === 0) {
    return (
      <div className="text-center text-gray-500 py-12">
        <CheckCircle className="w-12 h-12 mx-auto mb-4 text-green-500" />
        <p className="text-lg font-medium">No pending approvals</p>
        <p className="text-sm">All orders have been reviewed</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold flex items-center gap-2">
        <AlertCircle className="w-5 h-5 text-yellow-600" />
        Pending Approvals ({orders.length})
      </h2>

      {orders.map((order) => {
        const amount = parseFloat(order.total_amount.replace(/[R,]/g, ''));
        const isHighValue = amount > 5000;

        return (
          <div key={order.id} className="bg-white border rounded-lg p-4 shadow-sm">
            <div className="flex justify-between items-start mb-3">
              <div>
                <p className="font-semibold text-sm">
                  Order {order.id.slice(-6).toUpperCase()}
                </p>
                <p className="text-xs text-gray-600 mt-1">
                  Technician: <span className="font-medium">{order.technician_id}</span> • {order.site_id}
                </p>
                <p className="text-xs text-gray-600">
                  Requested: {new Date(order.created_at).toLocaleString()}
                </p>
              </div>
              <div className="text-right">
                <p className={`text-xl font-bold ${isHighValue ? 'text-red-600' : 'text-green-600'}`}>
                  {order.total_amount}
                </p>
                {isHighValue && (
                  <p className="text-xs text-red-600 mt-1 font-medium">
                    Requires approval (over R5,000)
                  </p>
                )}
              </div>
            </div>

            <div className="mb-4 bg-gray-50 rounded p-3">
              <p className="text-sm font-medium text-gray-700 mb-2">Items:</p>
              <ul className="text-sm space-y-1">
                {order.items.map((item, idx) => (
                  <li key={idx} className="flex justify-between items-start">
                    <span>
                      {item.quantity}x <span className="font-medium">{item.part_name}</span>
                      <br />
                      <span className="text-xs text-gray-600">
                        {item.part_number} • {item.supplier}
                      </span>
                    </span>
                    <span className="font-medium text-gray-700">
                      {item.unit_price}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => onApprove(order.id)}
                disabled={loading}
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 font-medium flex items-center justify-center gap-2 transition-colors"
              >
                <CheckCircle className="w-4 h-4" />
                Approve
              </button>
              <button
                onClick={() => onReject(order.id)}
                disabled={loading}
                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-400 font-medium flex items-center justify-center gap-2 transition-colors"
              >
                <XCircle className="w-4 h-4" />
                Reject
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
