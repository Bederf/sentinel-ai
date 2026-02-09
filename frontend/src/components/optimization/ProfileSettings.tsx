import React, { useState, useEffect } from 'react'
import type { SiteProfileConfig } from '@/lib/api/optimization'
import { optimizationApi } from '@/lib/api/optimization'

interface ProfileSettingsProps {
  siteId: string
  onProfileChange: (profile: string) => void
}

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
  }, [siteId])

  const loadProfileConfig = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await optimizationApi.getProfileSettings(siteId)
      setConfig(data)
      setSelectedProfile(data.active_profile)
      setZoneOverrides(data.zone_overrides || [])
    } catch (error) {
      console.error('Failed to load profile config:', error)
      setError('Failed to load profile configuration')
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
    } catch (error) {
      console.error('Failed to update profile:', error)
      setError('Failed to update profile')
    }
  }

  const handleRemoveZoneOverride = async (zoneId: string) => {
    const updated = zoneOverrides.filter((z) => z.zone_id !== zoneId)
    setZoneOverrides(updated)
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 text-center">
        <p className="text-gray-600">Loading profile configuration...</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-2xl font-bold mb-6">Optimization Profile</h2>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-800 rounded">
          {error}
        </div>
      )}

      {/* Active Profile Selector */}
      <div className="mb-6">
        <label className="block text-sm font-medium mb-2">
          Active Profile
        </label>
        <div className="grid grid-cols-3 gap-4">
          {['sweat_assets', 'comfort_first', 'cost_saving'].map((profile) => (
            <button
              key={profile}
              onClick={() => handleProfileChange(profile)}
              className={`p-4 border-2 rounded-lg transition ${
                selectedProfile === profile
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="font-semibold">
                {profile === 'sweat_assets' && 'Asset Sweating'}
                {profile === 'comfort_first' && 'Comfort First'}
                {profile === 'cost_saving' && 'Cost Saving'}
              </div>
              <div className="text-sm text-gray-600 mt-2">
                {getProfileDescription(profile)}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Control Tier */}
      <div className="mb-6">
        <label className="block text-sm font-medium mb-2">Control Tier</label>
        <select
          className="w-full px-4 py-2 border rounded-lg"
          defaultValue={config?.control_tier || 'human_in_loop'}
        >
          <option value="monitor">Monitor (Display Only)</option>
          <option value="human_in_loop">Human In Loop (Require Approval)</option>
          <option value="auto_execute">Auto Execute (Smart Tier 3)</option>
        </select>
      </div>

      {/* Zone Overrides Table */}
      <div className="mb-6">
        <h3 className="text-lg font-semibold mb-3">Zone Overrides</h3>
        {zoneOverrides.length === 0 ? (
          <p className="text-gray-600 text-sm mb-4">
            No zone overrides configured
          </p>
        ) : (
          <table className="w-full border-collapse mb-4">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 font-semibold">Zone ID</th>
                <th className="text-left py-2 font-semibold">Profile</th>
                <th className="text-left py-2 font-semibold">Reason</th>
                <th className="text-left py-2 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {zoneOverrides.map((override, idx) => (
                <tr key={idx} className="border-b hover:bg-gray-50">
                  <td className="py-2">{override.zone_id}</td>
                  <td className="py-2">{override.profile}</td>
                  <td className="py-2 text-sm">{override.reason}</td>
                  <td className="py-2">
                    <button
                      onClick={() => handleRemoveZoneOverride(override.zone_id)}
                      className="text-red-600 hover:underline text-sm"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <button className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
          Add Zone Override
        </button>
      </div>
    </div>
  )
}

function getProfileDescription(profile: string): string {
  const descriptions: Record<string, string> = {
    sweat_assets:
      'Maximize equipment utilization, defer replacements, higher maintenance risk',
    comfort_first:
      'Tight temp control, fast response, accept higher costs',
    cost_saving: 'Minimize operational spend, wider comfort bands, energy focus',
  }
  return descriptions[profile] || ''
}
