import React, { useState, useEffect } from 'react'
import { TrendingUp } from 'lucide-react'
import type { Recommendation } from '@/lib/api/optimization'
import { optimizationApi } from '@/lib/api/optimization'
import { Panel } from '../Panel'
import { EmptyState } from '../EmptyState'

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
    if (!siteId) return
    loadHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, filter])

  const loadHistory = async () => {
    if (!siteId) return
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
      <div
        className="rounded-lg p-6 text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading recommendation history...</p>
      </div>
    )
  }

  const filteredHistory = filter === 'all'
    ? history
    : filter === 'executed'
      ? history.filter(r => r.status === 'executed' || r.status === 'auto_executed')
      : history.filter(r => r.status === filter)

  return (
    <Panel
      header={{
        icon: <TrendingUp className="h-5 w-5" />,
        title: "Execution History",
        accentColor: "var(--color-sentinel-green)",
      }}
    >
      {error && (
        <div
          className="mx-4 mt-4 p-4 rounded text-sm"
          style={{
            background: "rgba(239, 68, 68, 0.08)",
            border: "1px solid var(--color-sentinel-red)",
            color: "var(--color-sentinel-red)",
          }}
        >
          {error}
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-2 p-4">
        {[
          { key: 'all', label: 'All' },
          { key: 'executed', label: 'Executed' },
          { key: 'rejected', label: 'Rejected' },
        ].map(f => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className="px-4 py-1.5 rounded text-xs font-medium transition-colors"
            style={{
              background: filter === f.key
                ? "var(--color-sentinel-amber)"
                : "var(--color-sentinel-bg-secondary)",
              color: filter === f.key
                ? "white"
                : "var(--color-sentinel-text-secondary)",
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Table */}
      {filteredHistory.length === 0 ? (
        <EmptyState
          icon={TrendingUp}
          title="No recommendations found"
          subtext="Recommendations will appear here once executed or reviewed."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                {['Action', 'Profile', 'Expected', 'Actual', 'Outcome', 'Status', 'Date'].map(h => (
                  <th
                    key={h}
                    className="text-left py-3 pr-4 font-medium text-xs uppercase tracking-wider"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredHistory.map((rec) => (
                <tr
                  key={rec.id}
                  style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
                >
                  <td className="py-3 pr-4">
                    <div
                      className="font-semibold text-sm"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {rec.action_type}
                    </div>
                    <div
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      {rec.target_equipment}
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <span
                      className="px-2 py-1 rounded text-xs font-medium"
                      style={{
                        background: "rgba(59, 130, 246, 0.15)",
                        color: "var(--color-sentinel-blue)",
                      }}
                    >
                      {rec.profile ?? '--'}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {rec.expected_impact?.cost_zar
                      ? `R${rec.expected_impact.cost_zar}`
                      : '--'}
                  </td>
                  <td className="py-3 pr-4 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {rec.actual_saving_zar
                      ? `R${rec.actual_saving_zar}`
                      : rec.outcome && rec.outcome.accuracy >= 0
                        ? '⏳ Pending'
                        : '--'}
                  </td>
                  <td className="py-3 pr-4">
                    {rec.outcome_validated === true ? (
                      <span style={{ color: "var(--color-sentinel-green)" }}>✅ Verified</span>
                    ) : rec.outcome_validated === false ? (
                      <span style={{ color: "var(--color-sentinel-red)" }}>❌ No gain</span>
                    ) : rec.status === 'executed' || rec.status === 'auto_executed' ? (
                      <span style={{ color: "var(--color-sentinel-amber)" }}>⏳ Verifying</span>
                    ) : (
                      <span style={{ color: "var(--color-sentinel-text-disabled)" }}>—</span>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    <span
                      className="px-3 py-1 rounded text-xs font-medium"
                      style={getStatusBadgeStyles(rec.status)}
                    >
                      {rec.status}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {rec.executed_at || rec.timestamp
                      ? new Date(rec.executed_at || rec.timestamp).toLocaleDateString()
                      : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

function getStatusBadgeStyles(status: string): React.CSSProperties {
  const map: Record<string, { bg: string; color: string }> = {
    executed: { bg: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" },
    rejected: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--color-sentinel-red)" },
    pending: { bg: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" },
    auto_executed: { bg: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" },
  }
  const s = map[status] ?? { bg: "rgba(148, 163, 184, 0.15)", color: "var(--color-sentinel-text-secondary)" }
  return { background: s.bg, color: s.color }
}
