import React, { useState, useEffect } from 'react'
import { TrendingUp } from 'lucide-react'
import type { Recommendation } from '@/lib/api/optimization'
import { optimizationApi } from '@/lib/api/optimization'
import { Panel } from '../Panel'
import { EmptyState } from '../EmptyState'

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
  const [isAdvisory, setIsAdvisory] = useState(false)

  useEffect(() => {
    // Fetch optimization status to determine control tier
    import('@/lib/api').then(({ api }) => {
      api.getOptimizationStatus(siteId).then((d: any) => {
        const mode = d?.optimization_settings?.mode || d?.optimization_status || '';
        setIsAdvisory(mode === 'advisory' || mode === 'shadow' || mode === 'monitor');
      }).catch(() => {});
    }).catch(() => {});
  }, [siteId])

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
      <div
        className="rounded-lg p-6 text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading recommendations...</p>
      </div>
    )
  }

  if (recommendations.length === 0) {
    return (
      <Panel>
        <EmptyState
          icon={TrendingUp}
          title="No pending recommendations"
          subtext="AI-generated recommendations will appear here when available."
        />
      </Panel>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h2
          className="text-lg font-semibold"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          Pending Recommendations
        </h2>
        <p
          className="text-xs italic"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          AI-generated recommendations &middot; Review before acting
        </p>
      </div>

      {error && (
        <div
          className="p-4 rounded text-sm"
          style={{
            background: "rgba(239, 68, 68, 0.08)",
            border: "1px solid var(--color-sentinel-red)",
            color: "var(--color-sentinel-red)",
          }}
        >
          {error}
        </div>
      )}

      {recommendations.map((rec) => (
        <div
          key={rec.id}
          className="rounded-lg p-6"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
            borderLeft: "4px solid var(--color-sentinel-blue)",
          }}
        >
          {/* Header */}
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3
                className="text-base font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {rec.recommendation_type?.replace(/_/g, " ") || "Recommendation"}
              </h3>
              <p
                className="text-sm"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {rec.title?.split(":")[0]?.trim() || rec.title || "--"}
              </p>
            </div>
            <div className="flex gap-2">
              <span
                className="px-3 py-1 rounded text-sm font-medium"
                style={getRiskBadgeStyles(rec.priority || "low")}
              >
                {rec.priority || "low"}
              </span>
              <span
                className="px-3 py-1 rounded text-sm font-medium"
                style={{
                  background: "rgba(59, 130, 246, 0.15)",
                  color: "var(--color-sentinel-blue)",
                }}
              >
                Score: {typeof rec.confidence === 'number' ? (rec.confidence * 100).toFixed(0) + '%' : '--'}
              </span>
            </div>
          </div>

          {/* Reason */}
          <div className="mb-4">
            <h4
              className="font-semibold text-xs uppercase tracking-wider mb-1"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Details
            </h4>
            <p
              className="text-sm"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {rec.description || rec.title || "--"}
            </p>
          </div>

          {/* Expected Impact */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div
              className="p-3 rounded"
              style={{ background: "rgba(16, 185, 129, 0.08)" }}
            >
              <p
                className="text-xs mb-1"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Cost Saving
              </p>
              <p
                className="text-lg font-bold"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                {rec.expected_impact
                  ? `R${typeof rec.expected_impact.cost_zar === 'number' ? rec.expected_impact.cost_zar.toFixed(2) : '0'}`
                  : 'R0'}
              </p>
            </div>
            <div
              className="p-3 rounded"
              style={{ background: "rgba(59, 130, 246, 0.08)" }}
            >
              <p
                className="text-xs mb-1"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Comfort Impact
              </p>
              <p
                className="text-lg font-bold"
                style={{ color: "var(--color-sentinel-blue)" }}
              >
                {rec.expected_impact
                  ? `${typeof rec.expected_impact.comfort_delta === 'number' ? rec.expected_impact.comfort_delta.toFixed(1) : '0'}°C`
                  : '0°C'}
              </p>
            </div>
            <div
              className="p-3 rounded"
              style={{ background: "rgba(167, 139, 250, 0.08)" }}
            >
              <p
                className="text-xs mb-1"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Energy Saving
              </p>
              <p
                className="text-lg font-bold"
                style={{ color: "#a78bfa" }}
              >
                {rec.expected_impact
                  ? `${typeof rec.expected_impact.energy_kwh === 'number' ? rec.expected_impact.energy_kwh.toFixed(1) : '0'} kWh`
                  : '0 kWh'}
              </p>
            </div>
          </div>

          {/* Actions */}
          {isAdvisory ? (
            <div
              className="p-3 rounded text-center text-sm"
              style={{
                background: "rgba(245, 158, 11, 0.1)",
                border: "1px solid rgba(245, 158, 11, 0.3)",
                color: "var(--color-sentinel-amber)",
              }}
            >
              Review and apply manually in BMS
            </div>
          ) : (
          <div className="flex gap-3">
            <button
              onClick={() => handleApprove(rec.id)}
              className="flex-1 px-4 py-2 rounded font-medium text-sm transition-opacity hover:opacity-90"
              style={{
                background: "var(--color-sentinel-green)",
                color: "white",
              }}
            >
              Approve
            </button>
            <button
              onClick={() => setSelectedRec(rec.id)}
              className="flex-1 px-4 py-2 rounded font-medium text-sm transition-opacity hover:opacity-90"
              style={{
                background: "var(--color-sentinel-red)",
                color: "white",
              }}
            >
              Reject
            </button>
          </div>
          )}

          {/* Rejection Modal */}
          {selectedRec === rec.id && (
            <div
              className="mt-4 p-4 rounded"
              style={{
                background: "rgba(239, 68, 68, 0.08)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
              }}
            >
              <p
                className="font-semibold text-sm mb-2"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Rejection Reason
              </p>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                className="w-full px-3 py-2 rounded text-sm"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
                placeholder="Why are you rejecting this recommendation?"
                rows={3}
              />
              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => handleReject(rec.id)}
                  className="px-4 py-2 rounded text-sm font-medium transition-opacity hover:opacity-90"
                  style={{
                    background: "var(--color-sentinel-red)",
                    color: "white",
                  }}
                >
                  Confirm Rejection
                </button>
                <button
                  onClick={() => {
                    setSelectedRec(null)
                    setRejectionReason('')
                  }}
                  className="px-4 py-2 rounded text-sm font-medium transition-opacity hover:opacity-90"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    color: "var(--color-sentinel-text-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                  }}
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

function getRiskBadgeStyles(risk: string): React.CSSProperties {
  const colors: Record<string, { bg: string; color: string }> = {
    low: { bg: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" },
    medium: { bg: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" },
    high: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--color-sentinel-red)" },
    critical: { bg: "rgba(167, 139, 250, 0.15)", color: "#a78bfa" },
  }
  const style = colors[risk] ?? { bg: "rgba(148, 163, 184, 0.15)", color: "var(--color-sentinel-text-secondary)" }
  return { background: style.bg, color: style.color }
}
