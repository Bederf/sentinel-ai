import { useState, useEffect } from 'react'
import { Briefcase, Clock, CheckCircle, Package } from 'lucide-react'
import type { ReactElement } from 'react'
import { authorizedFetch } from '../lib/api/client'

interface Order {
  id: string
  items: Array<{ part_name: string; quantity: number }>
  status: 'pending' | 'approved' | 'shipped' | 'delivered' | 'rejected'
  total_amount: number
  created_at?: string
}

interface DashboardData {
  assignedOrders: number
  pendingApprovals: number
  ordersInProgress: number
  completedThisWeek: number
  recentOrders: Order[]
}

export default function TechnicianPortal(): ReactElement {
  const [data, setData] = useState<DashboardData>({
    assignedOrders: 0,
    pendingApprovals: 0,
    ordersInProgress: 0,
    completedThisWeek: 0,
    recentOrders: [],
  })
  const [selectedTab, setSelectedTab] = useState<'overview' | 'orders' | 'approvals'>('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchDashboardData()
  }, [])

  const fetchDashboardData = async () => {
    try {
      setLoading(true)
      const response = await authorizedFetch('/api/technician/dashboard')
      if (response.status === 401) {
        setError('Session expired. Please sign in again.')
        return
      }
      if (response.status === 403) {
        setError('Maintenance module is not active for this site.')
        return
      }
      if (!response.ok) {
        throw new Error('Failed to load dashboard')
      }
      const dashboardData: DashboardData = await response.json()
      setData(dashboardData)
      setError(null)
    } catch (err) {
      console.error('Failed to load dashboard:', err)
      setError('Failed to load dashboard data')
      // Set mock data for local fallback mode
      setData({
        assignedOrders: 5,
        pendingApprovals: 2,
        ordersInProgress: 3,
        completedThisWeek: 4,
        recentOrders: [
          {
            id: 'ORD-001',
            items: [{ part_name: 'Bearing', quantity: 2 }],
            status: 'pending',
            total_amount: 1250,
          },
          {
            id: 'ORD-002',
            items: [{ part_name: 'Filter', quantity: 1 }],
            status: 'shipped',
            total_amount: 450,
          },
        ],
      })
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p style={{ color: "var(--color-sentinel-text-disabled)" }}>Loading dashboard...</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      {/* Header */}
      <div className="bg-white border-b px-4 py-3">
        <h1 className="text-xl font-semibold">Technician Portal</h1>
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Welcome back</p>
        {error && <p style={{ color: "var(--color-sentinel-red)" }}>{error}</p>}
      </div>

      {/* Tabs */}
      <div style={{ background: "var(--color-sentinel-bg-panel)", borderBottom: "1px solid var(--color-sentinel-border)" }} className="px-4 flex gap-4">
        <button
          onClick={() => setSelectedTab('overview')}
          className={`py-3 px-2 border-b-2 transition ${
            selectedTab === 'overview'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent' style={{ color: "var(--color-sentinel-text-secondary)" }}
          }`}
        >
          Overview
        </button>
        <button
          onClick={() => setSelectedTab('orders')}
          className={`py-3 px-2 border-b-2 transition ${
            selectedTab === 'orders'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent' style={{ color: "var(--color-sentinel-text-secondary)" }}
          }`}
        >
          My Orders
        </button>
        <button
          onClick={() => setSelectedTab('approvals')}
          className={`py-3 px-2 border-b-2 transition ${
            selectedTab === 'approvals'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent' style={{ color: "var(--color-sentinel-text-secondary)" }}
          }`}
        >
          Pending Approvals
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {selectedTab === 'overview' && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              icon={Briefcase}
              label="Assigned Jobs"
              value={data.assignedOrders}
              color="blue"
            />
            <StatCard
              icon={Clock}
              label="Pending Approvals"
              value={data.pendingApprovals}
              color="orange"
            />
            <StatCard
              icon={Package}
              label="Orders In Progress"
              value={data.ordersInProgress}
              color="purple"
            />
            <StatCard
              icon={CheckCircle}
              label="Completed This Week"
              value={data.completedThisWeek}
              color="green"
            />
          </div>
        )}

        {selectedTab === 'orders' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">My Orders</h2>
            {data.recentOrders.length === 0 ? (
              <p className="text-gray-500">No orders yet</p>
            ) : (
              <div className="space-y-2">
                {data.recentOrders.map((order) => (
                  <OrderCard key={order.id} order={order} />
                ))}
              </div>
            )}
          </div>
        )}

        {selectedTab === 'approvals' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Pending Approvals</h2>
            {data.recentOrders.filter((o) => o.status === 'pending').length === 0 ? (
              <p className="text-gray-500">No orders pending approval</p>
            ) : (
              <div className="space-y-2">
                {data.recentOrders
                  .filter((o) => o.status === 'pending')
                  .map((order) => (
                    <OrderCard key={order.id} order={order} showApprovalActions />
                  ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: number
  color: 'blue' | 'orange' | 'purple' | 'green'
}

function StatCard({ icon: Icon, label, value, color }: StatCardProps): ReactElement {
  const bgColor =
    color === 'blue'
      ? 'bg-blue-100'
      : color === 'orange'
        ? 'bg-orange-100'
        : color === 'purple'
          ? 'bg-purple-100'
          : 'bg-green-100'

  const textColor =
    color === 'blue'
      ? 'text-blue-600'
      : color === 'orange'
        ? 'text-orange-600'
        : color === 'purple'
          ? 'text-purple-600'
          : 'text-green-600'

  return (
    <div className="bg-white border rounded-lg p-4">
      <div className={`inline-flex p-2 rounded-lg mb-2 ${bgColor}`}>
        <Icon className={`w-6 h-6 ${textColor}`} />
      </div>
      <p className="text-sm text-gray-600 mb-1">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  )
}

interface OrderCardProps {
  order: Order
  showApprovalActions?: boolean
}

function OrderCard({ order, showApprovalActions }: OrderCardProps): ReactElement {
  const statusColors: Record<Order['status'], { bg: string; text: string }> = {
    pending: { bg: 'bg-yellow-100', text: 'text-yellow-700' },
    approved: { bg: 'bg-blue-100', text: 'text-blue-700' },
    shipped: { bg: 'bg-blue-100', text: 'text-blue-700' },
    delivered: { bg: 'bg-green-100', text: 'text-green-700' },
    rejected: { bg: 'bg-red-100', text: 'text-red-700' },
  }

  const colors = statusColors[order.status]

  const handleApprove = async () => {
    try {
      const response = await fetch(`/api/approval/${order.id}/approve`, {
        method: 'POST',
      })
      if (response.ok) {
        alert('Order approved!')
        window.location.reload()
      } else {
        alert('Failed to approve order')
      }
    } catch (error) {
      console.error('Error approving order:', error)
      alert('Error approving order')
    }
  }

  const handleReject = async () => {
    const reason = prompt('Enter rejection reason:')
    if (reason) {
      try {
        const response = await fetch(`/api/approval/${order.id}/reject`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason }),
        })
        if (response.ok) {
          alert('Order rejected!')
          window.location.reload()
        } else {
          alert('Failed to reject order')
        }
      } catch (error) {
        console.error('Error rejecting order:', error)
        alert('Error rejecting order')
      }
    }
  }

  return (
    <div className="bg-white border rounded-lg p-4">
      <div className="flex justify-between items-start mb-2">
        <div>
          <p className="font-medium">{order.id}</p>
          <p style={{ color: "var(--color-sentinel-text-secondary)" }}>{order.items.length} items</p>
        </div>
        <span className={`text-xs px-2 py-1 rounded ${colors.bg} ${colors.text}`}>
          {order.status}
        </span>
      </div>
      <p className="text-sm font-medium mb-3">R{order.total_amount.toFixed(2)}</p>

      {showApprovalActions && order.status === 'pending' && (
        <div className="flex gap-2">
          <button
            onClick={handleApprove}
            className="flex-1 px-3 py-2 text-sm rounded"
            style={{ background: "var(--color-sentinel-green)", color: "#fff" }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--color-sentinel-green-hover, #16a34a)")}
            onMouseLeave={e => (e.currentTarget.style.background = "var(--color-sentinel-green)")}
          >
            Approve
          </button>
          <button
            onClick={handleReject}
            className="flex-1 px-3 py-2 text-sm rounded"
            style={{ background: "var(--color-sentinel-red)", color: "#fff" }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--color-sentinel-red-hover, #dc2626)")}
            onMouseLeave={e => (e.currentTarget.style.background = "var(--color-sentinel-red)")}
          >
            Reject
          </button>
        </div>
      )}

      {order.status === 'shipped' && (
        <div className="text-xs mt-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
          <p>Track delivery status in your orders list</p>
        </div>
      )}
    </div>
  )
}
