import React, { useState, useEffect } from 'react'
import type { SiteProfileConfig } from '@/lib/api/optimization'
import { optimizationApi } from '@/lib/api/optimization'

interface ProfileSettingsProps {
  siteId: string
  onProfileChange: (profile: string) => void
}

const PROFILES = [
  {
    id: 'sweat_assets',
    label: 'Asset Sweating',
    description: 'Maximize utilization, defer replacements, accept higher maintenance risk',
  },
  {
    id: 'comfort_first',
    label: 'Comfort First',
    description: 'Tight temp control, fast response, accept higher energy cost',
  },
  {
    id: 'cost_saving',
    label: 'Cost Saving',
    description: 'Minimize spend, wider comfort bands, energy focus',
  },
]

export const ProfileSettings: React.FC<ProfileSettingsProps> = ({
  siteId,
  onProfileChange,
}) => {
  const [config, setConfig] = useState<SiteProfileConfig | null>(null)
  const [selectedProfile, setSelectedProfile] = useState<string>('cost_saving')
  const [zoneOverrides, setZoneOverrides] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadProfileConfig()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId])

  const loadProfileConfig = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await optimizationApi.getProfileSettings(siteId)
      setConfig(data)
      setSelectedProfile(data.active_profile)
      setZoneOverrides(data.zone_overrides || [])
    } catch {
      setError('Profile configuration unavailable')
    } finally {
      setLoading(false)
    }
  }

  const handleProfileChange = async (profile: string) => {
    try {
      await optimizationApi.updateProfileSettings(siteId, {
        active_profile: profile,
        control_tier: config?.control_tier || 'human_in_loop',
      })
      setSelectedProfile(profile)
      onProfileChange(profile)
      setError(null)
    } catch {
      setError('Failed to update profile')
    }
  }

  const handleRemoveZoneOverride = async (zoneId: string) => {
    setZoneOverrides((prev) => prev.filter((z) => z.zone_id !== zoneId))
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
        <div className="h-5 w-40 rounded animate-pulse mb-6" style={{ background: 'var(--color-sentinel-border)' }} />
        <div className="grid grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-24 rounded-xl animate-pulse"
              style={{ background: 'var(--color-sentinel-border)' }}
            />
          ))}
        </div>
      </div>
    )
  }

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

      {/* Graceful empty state — no red */}
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

      {/* Profile selector cards */}
      <div className="mb-5">
        <label
          className="block text-xs font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Active Profile
        </label>
        <div className="grid grid-cols-3 gap-3">
          {PROFILES.map((profile) => {
            const active = selectedProfile === profile.id
            return (
              <button
                key={profile.id}
                onClick={() => handleProfileChange(profile.id)}
                className="flex flex-col items-start text-left rounded-xl border-2 p-4 min-h-[90px] transition-colors"
                style={{
                  borderColor: active
                    ? 'var(--color-sentinel-blue)'
                    : 'var(--color-sentinel-border)',
                  background: active
                    ? 'rgba(59,130,246,0.08)'
                    : 'var(--color-sentinel-bg-canvas)',
                }}
              >
                <span
                  className="text-sm font-semibold leading-snug mb-1"
                  style={{
                    color: active
                      ? 'var(--color-sentinel-blue)'
                      : 'var(--color-sentinel-text-primary)',
                  }}
                >
                  {profile.label}
                </span>
                <span
                  className="text-xs leading-relaxed"
                  style={{ color: 'var(--color-sentinel-text-secondary)' }}
                >
                  {profile.description}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Control Tier — styled consistently */}
      <div className="mb-5">
        <label
          className="block text-xs font-medium uppercase tracking-wider mb-2"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Control Tier
        </label>
        <select
          className="w-full px-3 py-2 rounded-lg text-sm border outline-none"
          style={{
            background: 'var(--color-sentinel-bg-canvas)',
            borderColor: 'var(--color-sentinel-border)',
            color: 'var(--color-sentinel-text-primary)',
          }}
          defaultValue={config?.control_tier || 'human_in_loop'}
        >
          <option value="monitor">Monitor (Display Only)</option>
          <option value="human_in_loop">Human In Loop (Require Approval)</option>
          <option value="auto_execute">Auto Execute (Smart Tier 3)</option>
        </select>
      </div>

      {/* Zone Overrides */}
      <div>
        <h3
          className="text-sm font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Zone Overrides
        </h3>
        {zoneOverrides.length === 0 ? (
          <p className="text-sm mb-4" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            No zone overrides configured
          </p>
        ) : (
          <table className="w-full border-collapse mb-4 text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}>
                {['Zone ID', 'Profile', 'Reason', 'Actions'].map((h) => (
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
                <tr
                  key={idx}
                  style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
                >
                  <td className="py-2 pr-4" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {override.zone_id}
                  </td>
                  <td className="py-2 pr-4" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {override.profile}
                  </td>
                  <td className="py-2 pr-4 text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {override.reason}
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => handleRemoveZoneOverride(override.zone_id)}
                      className="text-xs hover:underline"
                      style={{ color: 'var(--color-sentinel-red)' }}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <button
          className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          style={{
            background: 'var(--color-sentinel-blue)',
            color: '#fff',
          }}
        >
          Add Zone Override
        </button>
      </div>
    </div>
  )
}
