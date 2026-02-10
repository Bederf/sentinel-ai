import { render, screen, fireEvent, waitFor } from '../../../test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ProfileSettings } from '../ProfileSettings'
import * as optimization from '@/lib/api/optimization'

vi.mock('@/lib/api/optimization', () => ({
  optimizationApi: {
    getProfileSettings: vi.fn(),
    updateProfileSettings: vi.fn(),
  },
}))

describe('ProfileSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders profile selector', async () => {
    vi.mocked(optimization.optimizationApi.getProfileSettings).mockResolvedValue({
      site_id: 'site-002',
      active_profile: 'cost_saving',
      control_tier: 'human_in_loop',
      zone_overrides: [],
    })

    render(
      <ProfileSettings
        siteId="site-002"
        onProfileChange={() => {}}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Comfort First')).toBeInTheDocument()
    })

    expect(screen.getByText('Asset Sweating')).toBeInTheDocument()
    expect(screen.getByText('Cost Saving')).toBeInTheDocument()
  })

  it('loads profile config on mount', async () => {
    const mockConfig: any = {
      site_id: 'site-002',
      active_profile: 'comfort_first',
      control_tier: 'auto_execute',
      zone_overrides: [
        {
          zone_id: 'zone-1',
          profile: 'cost_saving',
          reason: 'Off-peak hours',
        },
      ],
    }

    vi.mocked(optimization.optimizationApi.getProfileSettings).mockResolvedValue(mockConfig)

    render(
      <ProfileSettings
        siteId="site-002"
        onProfileChange={() => {}}
      />
    )

    await waitFor(() => {
      expect(optimization.optimizationApi.getProfileSettings).toHaveBeenCalledWith('site-002')
    })

    await waitFor(() => {
      expect(screen.getByText('zone-1')).toBeInTheDocument()
    })
  })

  it('calls API when profile changes', async () => {
    vi.mocked(optimization.optimizationApi.getProfileSettings).mockResolvedValue({
      site_id: 'site-002',
      active_profile: 'cost_saving',
      control_tier: 'human_in_loop',
      zone_overrides: [],
    })

    vi.mocked(optimization.optimizationApi.updateProfileSettings).mockResolvedValue({})

    const onProfileChange = vi.fn()

    render(
      <ProfileSettings
        siteId="site-002"
        onProfileChange={onProfileChange}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Asset Sweating')).toBeInTheDocument()
    })

    const sweatAssetsButton = screen.getByRole('button', {
      name: /Asset Sweating/,
    })
    fireEvent.click(sweatAssetsButton)

    await waitFor(() => {
      expect(optimization.optimizationApi.updateProfileSettings).toHaveBeenCalledWith(
        'site-002',
        expect.objectContaining({
          active_profile: 'sweat_assets',
          control_tier: 'human_in_loop',
        })
      )
    })

    expect(onProfileChange).toHaveBeenCalledWith('sweat_assets')
  })

  it('displays error when loading fails', async () => {
    vi.mocked(optimization.optimizationApi.getProfileSettings).mockRejectedValue(
      new Error('API error')
    )

    render(
      <ProfileSettings
        siteId="site-002"
        onProfileChange={() => {}}
      />
    )

    await waitFor(() => {
      expect(
        screen.getByText('Failed to load profile configuration')
      ).toBeInTheDocument()
    })
  })

  it('displays zone overrides', async () => {
    vi.mocked(optimization.optimizationApi.getProfileSettings).mockResolvedValue({
      site_id: 'site-002',
      active_profile: 'cost_saving',
      control_tier: 'human_in_loop',
      zone_overrides: [
        {
          zone_id: 'zone-1',
          profile: 'comfort_first',
          reason: 'Meeting room',
        },
        {
          zone_id: 'zone-2',
          profile: 'cost_saving',
          reason: 'Off-peak',
        },
      ],
    })

    render(
      <ProfileSettings
        siteId="site-002"
        onProfileChange={() => {}}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('zone-1')).toBeInTheDocument()
      expect(screen.getByText('zone-2')).toBeInTheDocument()
    })

    expect(screen.getByText('Meeting room')).toBeInTheDocument()
    expect(screen.getByText('Off-peak')).toBeInTheDocument()
  })

  it('can remove zone overrides', async () => {
    vi.mocked(optimization.optimizationApi.getProfileSettings).mockResolvedValue({
      site_id: 'site-002',
      active_profile: 'cost_saving',
      control_tier: 'human_in_loop',
      zone_overrides: [
        {
          zone_id: 'zone-1',
          profile: 'comfort_first',
          reason: 'Meeting room',
        },
      ],
    })

    render(
      <ProfileSettings
        siteId="site-002"
        onProfileChange={() => {}}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('zone-1')).toBeInTheDocument()
    })

    const removeButton = screen.getByRole('button', { name: /Remove/ })
    fireEvent.click(removeButton)

    await waitFor(() => {
      expect(screen.queryByText('zone-1')).not.toBeInTheDocument()
    })
  })
})
