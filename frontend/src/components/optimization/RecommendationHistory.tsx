import React, { useState, useEffect } from 'react'
import type { Recommendation } from '@/lib/api/optimization'
import { optimizationApi } from '@/lib/api/optimization'

interface RecommendationHistoryProps {
  siteId: string
}

export const RecommendationHistory: React.FC<
  RecommendationHistoryProps
> = ({ siteId }) => {
  const [history, setHistory] = useState<Recommendation[]>([])
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, filter])

  const loadHistory = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await optimizationApi.getHistory(siteId, {
        status: filter === 'all' ? undefined : filter,
      })
      setHistory(data.recommendations)
    } catch (error) {
      console.error('Failed to load history:', error)
      setError('Failed to load recommendation history')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 text-center">
        <p className="text-gray-600">Loading recommendation history...</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-2xl font-bold mb-6">Recommendation History</h2>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-800 rounded">
          {error}
        </div>
      )}

      {/* Filter */}
      <div className="mb-6 flex gap-2">
        <button
          onClick={() => setFilter('all')}
          className={`px-4 py-2 rounded ${
            filter === 'all'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          All
        </button>
        <button
          onClick={() => setFilter('executed')}
          className={`px-4 py-2 rounded ${
            filter === 'executed'
              ? 'bg-green-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Executed
        </button>
        <button
          onClick={() => setFilter('rejected')}
          className={`px-4 py-2 rounded ${
            filter === 'rejected'
              ? 'bg-red-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Rejected
        </button>
      </div>

      {/* Table */}
      {history.length === 0 ? (
        <p className="text-gray-600 text-center py-8">
          No recommendations found for the selected filter
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b">
                <th className="text-left py-3 font-semibold">Action</th>
                <th className="text-left py-3 font-semibold">Profile</th>
                <th className="text-left py-3 font-semibold">Score</th>
                <th className="text-left py-3 font-semibold">Status</th>
                <th className="text-left py-3 font-semibold">Accuracy</th>
                <th className="text-left py-3 font-semibold">Date</th>
              </tr>
            </thead>
            <tbody>
              {history.map((rec) => (
                <tr key={rec.id} className="border-b hover:bg-gray-50">
                  <td className="py-3">
                    <div className="font-semibold">{rec.action_type}</div>
                    <div className="text-sm text-gray-600">
                      {rec.target_equipment}
                    </div>
                  </td>
                  <td className="py-3">
                    <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-sm">
                      {rec.profile}
                    </span>
                  </td>
                  <td className="py-3">
                    {rec.multi_objective_score.toFixed(2)}
                  </td>
                  <td className="py-3">
                    <span
                      className={`px-3 py-1 rounded text-sm ${getStatusColor(
                        rec.status
                      )}`}
                    >
                      {rec.status}
                    </span>
                  </td>
                  <td className="py-3">
                    {rec.outcome ? (
                      <div className="flex items-center gap-2">
                        <div className="w-12 h-12 rounded-full bg-gray-200 flex items-center justify-center">
                          <span
                            className={
                              rec.outcome.accuracy > 0.8
                                ? 'text-green-600'
                                : rec.outcome.accuracy > 0.5
                                ? 'text-yellow-600'
                                : 'text-red-600'
                            }
                          >
                            {(rec.outcome.accuracy * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="text-sm">
                          <p className="font-semibold">
                            Pred: {rec.expected_impact.temperature_c?.toFixed(1)}°C
                          </p>
                          <p className="text-gray-600">
                            Actual:{' '}
                            {rec.outcome.actual.temperature_c?.toFixed(1)}°C
                          </p>
                        </div>
                      </div>
                    ) : (
                      <span className="text-gray-400 italic">Pending...</span>
                    )}
                  </td>
                  <td className="py-3 text-sm text-gray-600">
                    {new Date(rec.timestamp).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    executed: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
    pending: 'bg-yellow-100 text-yellow-800',
    auto_executed: 'bg-blue-100 text-blue-800',
  }
  return colors[status] || 'bg-gray-100 text-gray-800'
}
