import React, { useState, useEffect } from 'react'
import { Activity, CheckCircle, Clock, TrendingDown, TrendingUp } from 'lucide-react'
import type { Recommendation } from '@/lib/api/optimization'
import { optimizationApi } from '@/lib/api/optimization'
import { Panel } from '../Panel'
import { EmptyState } from '../EmptyState'
import { formatCurrencyZAR, formatNumber } from '@/lib/locale'

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
  }, [siteId])

  const loadHistory = async () => {
    if (!siteId) return
    try {
      setLoading(true)
      setError(null)
      const data = await optimizationApi.getHistory(siteId, {})
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

  const filteredHistory = filterRecommendations(history, filter)
  const visibleActionedCount = filteredHistory.filter(isActionedRecommendation).length
  const visibleVerifiedCount = filteredHistory.filter(isVerifiedRecommendation).length
  const visibleSavingKwh = filteredHistory.reduce((sum, rec) => sum + toNumber(rec.actual_saving_kwh), 0)
  const visibleSavingZar = filteredHistory.reduce((sum, rec) => sum + toNumber(rec.actual_saving_zar), 0)

  return (
    <Panel
      header={{
        icon: <Activity className="h-5 w-5" />,
        title: "AI Recommendation Outcomes",
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

      <div className="grid grid-cols-2 gap-3 p-4 md:grid-cols-4">
        <SummaryMetric label="Suggested" value={String(filteredHistory.length)} />
        <SummaryMetric label="Actioned" value={String(visibleActionedCount)} />
        <SummaryMetric label="Verified" value={String(visibleVerifiedCount)} />
        <SummaryMetric
          label="Measured Result"
          value={`${formatSignedKwh(visibleSavingKwh)} / ${formatCurrencyZAR(visibleSavingZar, 2, 2)}`}
          tone={visibleSavingKwh >= 0 ? 'positive' : 'negative'}
        />
      </div>

      {/* Filter */}
      <div className="flex gap-2 px-4 pb-4">
        {[
          { key: 'all', label: 'Total' },
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
          subtext="Recommendations will appear here once Sentinel has suggested, actioned, or verified an AI control decision."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                {['Suggested', 'Actioned', 'Measured Result', 'Outcome', 'Status', 'Date'].map(h => (
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
                      {formatSuggestedAction(rec)}
                    </div>
                    <div
                      className="mt-1 max-w-md text-xs"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      {rec.target_equipment}
                      {rec.reason ? ` · ${rec.reason}` : ''}
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <div className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {formatActionedValue(rec)}
                    </div>
                    <div className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {rec.approved_at ? `Approved ${new Date(rec.approved_at).toLocaleString()}` : 'Approval time not recorded'}
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <MeasuredResult rec={rec} />
                  </td>
                  <td className="py-3 pr-4">
                    {rec.outcome_validated === true ? (
                      <span className="inline-flex items-center gap-1 text-sm" style={{ color: "var(--color-sentinel-green)" }}>
                        <CheckCircle className="h-4 w-4" /> Verified
                      </span>
                    ) : rec.outcome_validated === false ? (
                      <span className="inline-flex items-center gap-1 text-sm" style={{ color: "var(--color-sentinel-red)" }}>
                        <TrendingDown className="h-4 w-4" /> No measured gain
                      </span>
                    ) : rec.status === 'executed' || rec.status === 'auto_executed' ? (
                      <span className="inline-flex items-center gap-1 text-sm" style={{ color: "var(--color-sentinel-amber)" }}>
                        <Clock className="h-4 w-4" /> Verifying
                      </span>
                    ) : (
                      <span style={{ color: "var(--color-sentinel-text-disabled)" }}>—</span>
                    )}
                    {rec.outcome_notes && (
                      <div className="mt-1 max-w-xs text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {rec.outcome_notes}
                      </div>
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

function SummaryMetric({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'neutral' | 'positive' | 'negative'
}) {
  const color = tone === 'positive'
    ? 'var(--color-sentinel-green)'
    : tone === 'negative'
      ? 'var(--color-sentinel-red)'
      : 'var(--color-sentinel-text-primary)'

  return (
    <div
      className="rounded-lg p-3"
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <p className="text-[10px] font-medium uppercase tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold tabular-nums" style={{ color }}>
        {value}
      </p>
    </div>
  )
}

function filterRecommendations(history: Recommendation[], filter: string): Recommendation[] {
  if (filter === 'executed') return history.filter(isActionedRecommendation)
  if (filter === 'rejected') return history.filter(rec => rec.status === 'rejected')
  return history
}

function isActionedRecommendation(rec: Recommendation): boolean {
  return rec.status === 'executed' || rec.status === 'auto_executed'
}

function isVerifiedRecommendation(rec: Recommendation): boolean {
  return rec.outcome_validated === true || rec.actual_saving_kwh != null || rec.actual_saving_zar != null
}

function MeasuredResult({ rec }: { rec: Recommendation }) {
  if (rec.actual_saving_kwh == null && rec.actual_saving_zar == null) {
    return (
      <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        {rec.status === 'executed' || rec.status === 'auto_executed' ? 'Awaiting 30 min verification' : '--'}
      </div>
    )
  }

  const savingKwh = toNumber(rec.actual_saving_kwh)
  const savingZar = toNumber(rec.actual_saving_zar)
  const color = savingKwh >= 0 ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-red)'

  return (
    <div>
      <div className="text-sm font-semibold tabular-nums" style={{ color }}>
        {formatSignedKwh(savingKwh)} / {formatCurrencyZAR(savingZar, 2, 2)}
      </div>
      {(rec.baseline_energy_kwh != null || rec.actual_energy_kwh != null) && (
        <div className="mt-1 text-xs tabular-nums" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Before {formatKwh(rec.baseline_energy_kwh)} · After {formatKwh(rec.actual_energy_kwh)}
        </div>
      )}
    </div>
  )
}

function formatSuggestedAction(rec: Recommendation): string {
  const point = getActionPoint(rec)
  const value = getActionValue(rec)
  if (point && value !== undefined && value !== null && value !== '') {
    return `${formatLabel(point)} to ${String(value)}${getActionUnit(rec)}`
  }
  if (rec.title) return rec.title
  if (rec.description) return rec.description
  return formatLabel(rec.action_type || 'AI recommendation')
}

function formatActionedValue(rec: Recommendation): string {
  if (rec.status !== 'executed' && rec.status !== 'auto_executed') {
    return rec.status === 'rejected' ? 'Not actioned' : 'Not executed'
  }

  const point = getActionPoint(rec)
  const value = getActionValue(rec)
  if (point && value !== undefined && value !== null && value !== '') {
    return `${rec.target_equipment}: ${formatLabel(point)} = ${String(value)}${getActionUnit(rec)}`
  }
  return `${rec.target_equipment}: executed`
}

function getActionPoint(rec: Recommendation): string | null {
  const action = rec.action || {}
  const value = (action as Record<string, unknown>).point ?? (action as Record<string, unknown>).parameter
  return typeof value === 'string' && value ? value : null
}

function getActionValue(rec: Recommendation): unknown {
  const action = rec.action || {}
  const data = action as Record<string, unknown>
  return data.value ?? data.target_value
}

function getActionUnit(rec: Recommendation): string {
  const unit = (rec.action as Record<string, unknown> | undefined)?.unit
  return typeof unit === 'string' && unit ? unit : ''
}

function formatLabel(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function formatKwh(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  return `${formatNumber(Number(value), 0, 2)} kWh`
}

function formatSignedKwh(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatNumber(value, 0, 2)} kWh`
}

function toNumber(value: number | null | undefined): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
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
