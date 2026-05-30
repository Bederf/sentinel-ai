import { useCallback, useMemo, useState } from 'react'
import type {
  CockpitIssueActionType,
  CockpitIssueItem,
  CockpitIssueSeverity,
  CockpitIssueSourceHealth,
  CockpitIssuesPayload,
  CockpitSourceHealthState,
} from './types'

// ─── Props ────────────────────────────────────────────────────────────────────

interface CockpitIssuePanelProps {
  payload: CockpitIssuesPayload | null
  onAction: (issueId: string, action: CockpitIssueActionType) => Promise<void>
  selectedIssueId: string | null
  onSelectIssue: (issueId: string) => void
}

// ─── Severity helpers ─────────────────────────────────────────────────────────

function severityBadgeClass(severity: CockpitIssueSeverity): string {
  switch (severity) {
    case 'critical':
      return 'bg-red-500/15 border-red-500/40 text-red-400'
    case 'high':
      return 'bg-orange-500/15 border-orange-500/40 text-orange-400'
    case 'medium':
      return 'bg-yellow-500/15 border-yellow-500/40 text-yellow-400'
    case 'low':
      return 'bg-zinc-700/40 border-zinc-600/50 text-zinc-400'
  }
}

function severityDotClass(severity: CockpitIssueSeverity): string {
  switch (severity) {
    case 'critical':
      return 'bg-red-500'
    case 'high':
      return 'bg-orange-500'
    case 'medium':
      return 'bg-yellow-500'
    case 'low':
      return 'bg-zinc-500'
  }
}

// ─── Source health helpers ────────────────────────────────────────────────────

function sourceHealthDotClass(state: CockpitSourceHealthState): string {
  switch (state) {
    case 'healthy':
      return 'bg-emerald-400'
    case 'stale':
      return 'bg-amber-400'
    case 'degraded':
      return 'bg-orange-500'
    case 'unavailable':
      return 'bg-zinc-600'
  }
}

// ─── SLA countdown helpers ────────────────────────────────────────────────────

function slaMinsRemaining(slaAt: string): number {
  return Math.round((new Date(slaAt).getTime() - Date.now()) / 60_000)
}

function slaLabel(minsRemaining: number): string {
  if (minsRemaining <= 0) return 'SLA breached'
  if (minsRemaining < 60) return `SLA: ${minsRemaining}m remaining`
  return `SLA: ${Math.round(minsRemaining / 60)}h remaining`
}

// ─── Action availability ──────────────────────────────────────────────────────

const POSTURE_ACTIONS: Record<string, CockpitIssueActionType[]> = {
  advisory: ['acknowledge'],
  supervised: ['acknowledge', 'assign', 'create_work_order'],
  auto: ['acknowledge', 'assign', 'create_work_order', 'escalate'],
}

function actionsForPosture(posture: string | null): CockpitIssueActionType[] {
  if (!posture) return ['acknowledge']
  return POSTURE_ACTIONS[posture] ?? ['acknowledge']
}

const ACTION_LABELS: Record<CockpitIssueActionType, string> = {
  acknowledge: 'Acknowledge',
  assign: 'Assign',
  create_work_order: 'Work Order',
  escalate: 'Escalate',
}

// ─── Action button ────────────────────────────────────────────────────────────

interface ActionButtonProps {
  action: CockpitIssueActionType
  available: boolean
  loading: boolean
  succeeded: boolean
  onClick: () => void
}

function ActionButton({ action, available, loading, succeeded, onClick }: ActionButtonProps) {
  const isPrimary = action === 'acknowledge'

  const base =
    'flex-1 rounded-lg border px-3 py-2 text-[10px] uppercase tracking-[0.18em] font-medium transition-all duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400'

  let coloring: string
  if (!available) {
    coloring = 'border-white/8 bg-white/[0.02] text-slate-600 cursor-not-allowed'
  } else if (succeeded) {
    coloring = 'border-emerald-400/40 bg-emerald-400/10 text-emerald-300'
  } else if (loading) {
    coloring = 'border-cyan-400/30 bg-cyan-400/8 text-cyan-400 cursor-wait'
  } else if (isPrimary) {
    coloring = 'border-cyan-400/40 bg-cyan-400/10 text-cyan-300 hover:bg-cyan-400/18'
  } else {
    coloring = 'border-white/12 bg-white/[0.04] text-slate-300 hover:bg-white/[0.08]'
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!available || loading}
      aria-label={ACTION_LABELS[action]}
      className={`${base} ${coloring}`}
    >
      {succeeded ? 'Done' : loading ? '...' : ACTION_LABELS[action]}
    </button>
  )
}

// ─── Source health row ────────────────────────────────────────────────────────

function SourceHealthRow({ sources }: { sources: CockpitIssueSourceHealth[] }) {
  return (
    <div className="flex items-center gap-3 px-5 py-3 border-b border-white/8">
      <span className="text-[9px] uppercase tracking-[0.2em] text-slate-600">Sources</span>
      <div className="flex items-center gap-3 ml-1">
        {sources.map((s) => (
          <div key={s.source} className="flex items-center gap-1.5" title={s.message}>
            <span className={`h-1.5 w-1.5 rounded-full ${sourceHealthDotClass(s.state)}`} />
            <span className="text-[10px] text-slate-400">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Issue list item ──────────────────────────────────────────────────────────

interface IssueListItemProps {
  issue: CockpitIssueItem
  isSelected: boolean
  onSelect: () => void
}

function IssueListItem({ issue, isSelected, onSelect }: IssueListItemProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full flex items-center gap-3 px-5 py-3 text-left transition-colors ${
        isSelected
          ? 'bg-white/[0.05] border-l-2 border-cyan-400/60'
          : 'border-l-2 border-transparent hover:bg-white/[0.03]'
      }`}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${severityDotClass(issue.severity)}`} />
      <span className="flex-1 truncate text-[11px] text-slate-300">{issue.title}</span>
      <span
        className={`shrink-0 rounded border px-2 py-0.5 text-[9px] uppercase tracking-[0.14em] ${severityBadgeClass(issue.severity)}`}
      >
        {issue.severity}
      </span>
    </button>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function CockpitIssuePanel({
  payload,
  onAction,
  selectedIssueId,
  onSelectIssue,
}: CockpitIssuePanelProps) {
  const [loadingAction, setLoadingAction] = useState<CockpitIssueActionType | null>(null)
  const [succeededAction, setSucceededAction] = useState<CockpitIssueActionType | null>(null)

  // Calm building state
  if (!payload || payload.issues.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 px-5 py-8 text-center">
        <span className="h-2 w-2 rounded-full bg-emerald-400/60" />
        <span className="text-[10px] uppercase tracking-[0.22em] text-slate-500">
          No active issues — building stable
        </span>
      </div>
    )
  }

  const resolvedSelectedId = selectedIssueId ?? payload.selectedIssueId ?? payload.issues[0]?.id ?? null
  const selectedIssue = payload.issues.find((i) => i.id === resolvedSelectedId) ?? payload.issues[0]

  const otherIssues = useMemo(
    () => payload.issues.filter((i) => i.id !== selectedIssue?.id),
    [payload.issues, selectedIssue?.id],
  )

  const availableActions = useMemo(
    () => actionsForPosture(payload.posture),
    [payload.posture],
  )

  const handleAction = useCallback(
    async (action: CockpitIssueActionType) => {
      if (!selectedIssue) return
      setLoadingAction(action)
      setSucceededAction(null)
      try {
        await onAction(selectedIssue.id, action)
        setSucceededAction(action)
        // Reset success flash after 1.8s
        setTimeout(() => setSucceededAction(null), 1800)
      } finally {
        setLoadingAction(null)
      }
    },
    [selectedIssue, onAction],
  )

  if (!selectedIssue) return null

  const slaMinutes =
    selectedIssue.sla_due_at ? slaMinsRemaining(selectedIssue.sla_due_at) : null
  const showSlaBadge = slaMinutes !== null && slaMinutes <= 60

  const ALL_ACTIONS: CockpitIssueActionType[] = ['acknowledge', 'assign', 'create_work_order', 'escalate']

  return (
    <div className="flex flex-col divide-y divide-white/8">
      {/* Source health bar */}
      {payload.sourceHealth.length > 0 && (
        <SourceHealthRow sources={payload.sourceHealth} />
      )}

      {/* Selected issue detail */}
      <div className="px-5 py-4 space-y-3">
        {/* Title + severity */}
        <div className="flex items-start gap-3">
          <span
            className={`mt-0.5 shrink-0 rounded border px-2 py-0.5 text-[9px] uppercase tracking-[0.14em] ${severityBadgeClass(selectedIssue.severity)}`}
          >
            {selectedIssue.severity}
          </span>
          <h3 className="flex-1 text-sm font-medium leading-snug text-slate-100">
            {selectedIssue.title}
          </h3>
        </div>

        {/* Summary */}
        <p className="text-xs leading-relaxed text-slate-400">{selectedIssue.summary}</p>

        {/* Recommended action */}
        {selectedIssue.recommended_action && (
          <div className="rounded-md border border-white/8 bg-white/[0.03] px-3 py-2">
            <span className="text-[9px] uppercase tracking-[0.18em] text-slate-500">
              Recommended
            </span>
            <p className="mt-1 text-[11px] text-slate-300">{selectedIssue.recommended_action}</p>
          </div>
        )}

        {/* Confidence + SLA row */}
        <div className="flex flex-wrap items-center gap-2">
          {selectedIssue.confidence_label && (
            <span className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-0.5 text-[9px] uppercase tracking-[0.14em] text-slate-400">
              {selectedIssue.confidence_label}
            </span>
          )}
          {showSlaBadge && (
            <span
              className={`rounded-full border px-2.5 py-0.5 text-[9px] uppercase tracking-[0.14em] ${
                (slaMinutes ?? 0) <= 0
                  ? 'border-red-500/50 bg-red-500/10 text-red-400'
                  : 'border-amber-400/40 bg-amber-400/8 text-amber-400'
              }`}
            >
              {slaLabel(slaMinutes ?? 0)}
            </span>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="px-5 py-3">
        <div className="mb-2 text-[9px] uppercase tracking-[0.18em] text-slate-600">Actions</div>
        <div className="flex gap-2">
          {ALL_ACTIONS.map((action) => (
            <ActionButton
              key={action}
              action={action}
              available={availableActions.includes(action)}
              loading={loadingAction === action}
              succeeded={succeededAction === action}
              onClick={() => handleAction(action)}
            />
          ))}
        </div>
      </div>

      {/* Other issues list */}
      {otherIssues.length > 0 && (
        <div>
          <div className="px-5 pt-3 pb-1 text-[9px] uppercase tracking-[0.18em] text-slate-600">
            Other issues ({otherIssues.length})
          </div>
          <div className="divide-y divide-white/[0.04]">
            {otherIssues.map((issue) => (
              <IssueListItem
                key={issue.id}
                issue={issue}
                isSelected={false}
                onSelect={() => onSelectIssue(issue.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
