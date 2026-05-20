/**
 * SafetyNoticeSection: Equipment-specific safety and escalation guidance
 */

import { AlertTriangle } from 'lucide-react'

interface SafetyNoticeSectionProps {
  message: string
}

export function SafetyNoticeSection({ message }: SafetyNoticeSectionProps) {
  const noticeStyle = {
    outer: {
      background: 'rgba(var(--color-sentinel-amber-rgb, 245,158,11), 0.08)',
      borderColor: 'rgba(var(--color-sentinel-amber-rgb, 245,158,11), 0.25)',
    },
    header: {
      background: 'rgba(var(--color-sentinel-amber-rgb, 245,158,11), 0.15)',
      borderColor: 'rgba(var(--color-sentinel-amber-rgb, 245,158,11), 0.25)',
    },
    iconColor: 'var(--color-sentinel-amber)',
    labelColor: 'var(--color-sentinel-amber)',
    bodyColor: 'var(--color-sentinel-text-primary)',
  }

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ background: noticeStyle.outer.background, borderColor: noticeStyle.header.borderColor }}
    >
      <div
        className="px-4 py-3 border-b"
        style={{ background: noticeStyle.header.background, borderColor: noticeStyle.header.borderColor }}
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" style={{ color: noticeStyle.iconColor }} />
          <p className="text-sm font-semibold uppercase tracking-wider" style={{ color: noticeStyle.labelColor }}>
            Safety Notice
          </p>
        </div>
      </div>
      <div className="px-4 py-3">
        <p className="text-sm" style={{ color: noticeStyle.bodyColor }}>{message}</p>
      </div>
    </div>
  )
}
