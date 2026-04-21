import React, { useState, useEffect } from 'react'
import type { Recommendation } from '@/lib/api/optimization'
import { optimizationApi } from '@/lib/api/optimization'

interface RecommendationsDashboardProps {
  siteId: string
}

export const RecommendationsDashboard: React.FC<
  RecommendationsDashboardProps
> = ({ siteId }) => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedRec, setSelectedRec] = useState<string | null>(null)
  const [rejectionReason, setRejectionReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadRecommendations()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId])

  const loadRecommendations = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await optimizationApi.getPending(siteId)
      setRecommendations(Array.isArray(data) ? data : (data as { recommendations: Recommendation[] }).recommendations)
    } catch (error) {
      console.error('Failed to load recommendations:', error)
      setError('Failed to load recommendations')
    } finally {
      setLoading(false)
    }
  }

  const handleApprove = async (recId: string) => {
    try {
      await optimizationApi.approve(recId, 'dashboard')
      setRecommendations((recs) =>
        recs.filter((r) => r.id !== recId)
      )
      setError(null)
    } catch (error) {
      console.error('Failed to approve:', error)
      setError('Failed to approve recommendation')
    }
  }

  const handleReject = async (recId: string) => {
    if (!rejectionReason.trim()) {
      setError('Please provide a rejection reason')
      return
    }

    try {
      await optimizationApi.reject(recId, 'dashboard', rejectionReason)
      setRecommendations((recs) =>
        recs.filter((r) => r.id !== recId)
      )
      setSelectedRec(null)
      setRejectionReason('')
      setError(null)
    } catch (error) {
      console.error('Failed to reject:', error)
      setError('Failed to reject recommendation')
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 text-center">
        <p className="text-gray-600">Loading recommendations...</p>
      </div>
    )
  }

  if (recommendations.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6 text-center">
        <p className="text-gray-600">No pending recommendations</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold">Pending Recommendations</h2>
        <p className="text-xs text-gray-400 italic mt-0.5">
          AI-generated recommendations &middot; Review before acting
        </p>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-800 rounded">
          {error}
        </div>
      )}

      {recommendations.map((rec) => (
        <div
          key={rec.id}
          className="bg-white rounded-lg shadow p-6 border-l-4 border-blue-500"
        >
          {/* Header */}
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3 className="text-lg font-semibold">{rec.action_type}</h3>
              <p className="text-sm text-gray-600">
                Target: {rec.target_equipment}
              </p>
            </div>
            <div className="flex gap-2">
              <span
                className={`px-3 py-1 rounded text-sm ${getRiskBadgeColor(
                  rec.risk_level
                )}`}
              >
                {rec.risk_level}
              </span>
              <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded text-sm">
                Score: {typeof rec.multi_objective_score === 'number' ? rec.multi_objective_score.toFixed(2) : '--'}
              </span>
            </div>
          </div>

          {/* Reason */}
          <div className="mb-4">
            <h4 className="font-semibold text-sm mb-1">Reason</h4>
            <p className="text-sm text-gray-700">{rec.reason}</p>
          </div>

          {/* Expected Impact */}
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="bg-green-50 p-3 rounded">
              <p className="text-xs text-gray-600">Cost Saving</p>
              <p className="text-lg font-bold text-green-700">
                {rec.expected_impact
                  ? `R${typeof rec.expected_impact.cost_zar === 'number' ? rec.expected_impact.cost_zar.toFixed(2) : '0'}`
                  : 'R0'}
              </p>
            </div>
            <div className="bg-blue-50 p-3 rounded">
              <p className="text-xs text-gray-600">Comfort Impact</p>
              <p className="text-lg font-bold text-blue-700">
                {rec.expected_impact
                  ? `${typeof rec.expected_impact.comfort_delta === 'number' ? rec.expected_impact.comfort_delta.toFixed(1) : '0'}°C`
                  : '0°C'}
              </p>
            </div>
            <div className="bg-purple-50 p-3 rounded">
              <p className="text-xs text-gray-600">Energy Saving</p>
              <p className="text-lg font-bold text-purple-700">
                {rec.expected_impact
                  ? `${typeof rec.expected_impact.energy_kwh === 'number' ? rec.expected_impact.energy_kwh.toFixed(1) : '0'} kWh`
                  : '0 kWh'}
              </p>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-4">
            <button
              onClick={() => handleApprove(rec.id)}
              className="flex-1 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
            >
              Approve
            </button>
            <button
              onClick={() => setSelectedRec(rec.id)}
              className="flex-1 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
            >
              Reject
            </button>
          </div>

          {/* Rejection Modal */}
          {selectedRec === rec.id && (
            <div className="mt-4 p-4 bg-red-50 rounded border border-red-200">
              <p className="font-semibold mb-2">Rejection Reason</p>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                className="w-full px-3 py-2 border rounded mb-3"
                placeholder="Why are you rejecting this recommendation?"
                rows={3}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => handleReject(rec.id)}
                  className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
                >
                  Confirm Rejection
                </button>
                <button
                  onClick={() => {
                    setSelectedRec(null)
                    setRejectionReason('')
                  }}
                  className="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function getRiskBadgeColor(risk: string): string {
  const colors: Record<string, string> = {
    low: 'bg-green-100 text-green-800',
    medium: 'bg-yellow-100 text-yellow-800',
    high: 'bg-red-100 text-red-800',
    critical: 'bg-purple-100 text-purple-800',
  }
  return colors[risk] || 'bg-gray-100 text-gray-800'
}
