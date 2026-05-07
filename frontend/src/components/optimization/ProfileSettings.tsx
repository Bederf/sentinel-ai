import React, { useState, useEffect } from 'react'
import type { SiteProfileConfig } from '@/lib/api/optimization'
import { optimizationApi } from '@/lib/api/optimization'

interface ProfileSettingsProps {
  siteId: string
  onProfileChange?: () => void
}

// Matches BuildingConfigEditor OPTIMIZATION_PROFILES naming
const PROFILE_OPTIONS = [
  { value: 'cost_saving', label: 'Cost Saving', desc: 'Minimize energy spend' },
  { value: 'comfort_first', label: 'Comfort First', desc: 'Prioritize occupant comfort' },
  { value: 'balanced', label: 'Balanced', desc: 'Balance cost and comfort' },
  { value: 'sweat_assets', label: 'Asset Sweating', desc: 'Protect building assets' },
]

const CONTROL_TIER_LABELS: Record<string, string> = {
  monitor: 'Monitor (Display Only)',
  human_in_loop: 'Human In Loop (Require Approval)',
  auto_execute: 'Auto Execute (Smart Tier 3)',
}

function getProfileLabel(profileId: string | null): string {
  if (!profileId) return '--'
  const found = PROFILE_OPTIONS.find(p => p.value === profileId)
  return found ? found.label : profileId
}

function getTierLabel(tier: string | null): string {
  return tier ? (CONTROL_TIER_LABELS[tier] ?? tier) : '--'
}

export const ProfileSettings: React.FC<ProfileSettingsProps> = ({ siteId }) => {
  const [config, setConfig] = useState<SiteProfileConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!siteId) return
    loadProfileConfig()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId])

  const loadProfileConfig = async () => {
    if (!siteId) return
    try {
      setLoading(true)
      setError(null)
      const data = await optimizationApi.getProfileSettings(siteId)
      setConfig(data)
    } catch {
      setError('Profile configuration unavailable')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div
        className="rounded-2xl border p-6"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          borderColor: 'var(--color-sentinel-border)',
        }}
      >
        <div className="h-5 w-48 rounded animate-pulse mb-6" style={{ background: 'var(--color-sentinel-border)' }} />
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-12 rounded-lg animate-pulse" style={{ background: 'var(--color-sentinel-border)' }} />
          ))}
        </div>
      </div>
    )
  }

  const activeProfile = config?.active_profile ?? null
  const controlTier = config?.control_tier ?? null
  const zoneOverrides = config?.zone_overrides ?? []

  return (
    <div
      className="rounded-2xl border p-6"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        borderColor: 'var(--color-sentinel-border)',
      }}
    >
      <h2
        className="text-lg font-semibold mb-5"
        style={{ color: 'var(--color-sentinel-text-primary)' }}
      >
        Optimization Profile
      </h2>

      {error && (
        <div
          className="mb-5 px-4 py-3 rounded-lg text-sm"
          style={{
            background: 'rgba(148,163,184,0.08)',
            border: '1px solid var(--color-sentinel-border)',
            color: 'var(--color-sentinel-text-secondary)',
          }}
        >
          {error}
        </div>
      )}

      {/* Active Profile — read-only indicator */}
      <div className="mb-6">
        <p
          className="block text-xs font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Active Profile
        </p>
        <div className="grid grid-cols-3 gap-3">
          {PROFILE_OPTIONS.map(p => {
            const active = activeProfile === p.value
            return (
              <div
                key={p.value}
                className="flex flex-col items-start text-left rounded-xl border-2 p-4 min-h-[90px]"
                style={{
                  borderColor: active ? 'var(--color-sentinel-blue)' : 'var(--color-sentinel-border)',
                  background: active ? 'rgba(59,130,246,0.08)' : 'var(--color-sentinel-bg-canvas)',
                  opacity: active ? 1 : 0.5,
                }}
              >
                <span
                  className="text-sm font-semibold leading-snug mb-1"
                  style={{ color: active ? 'var(--color-sentinel-blue)' : 'var(--color-sentinel-text-primary)' }}
                >
                  {p.label}
                </span>
                <span className="text-xs leading-relaxed" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  {p.desc}
                </span>
                {active && (
                  <span className="mt-auto pt-2 text-xs font-medium" style={{ color: 'var(--color-sentinel-blue)' }}>
                    Active
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Control Tier — read-only indicator */}
      <div className="mb-6">
        <p
          className="block text-xs font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Control Tier
        </p>
        <div
          className="w-full px-3 py-2 rounded-lg text-sm border"
          style={{
            background: 'var(--color-sentinel-bg-canvas)',
            borderColor: 'var(--color-sentinel-border)',
            color: 'var(--color-sentinel-text-primary)',
          }}
        >
          {getTierLabel(controlTier)}
        </div>
      </div>

      {/* Zone Overrides — read-only indicator */}
      <div>
        <p
          className="block text-sm font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Zone Overrides
        </p>
        {zoneOverrides.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            No zone overrides configured
          </p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}>
                {['Zone ID', 'Profile', 'Reason'].map(h => (
                  <th
                    key={h}
                    className="text-left py-2 pr-4 font-medium text-xs uppercase tracking-wider"
                    style={{ color: 'var(--color-sentinel-text-secondary)' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {zoneOverrides.map((override, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}>
                  <td className="py-2 pr-4" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {override.zone_id}
                  </td>
                  <td className="py-2 pr-4" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {getProfileLabel(override.profile)}
                  </td>
                  <td className="py-2 text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {override.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
