/**
 * Hook to check module activation status and fetch related recommendation data.
 * Used by LockedFeatureOverlay to determine if a feature is accessible.
 */

import { useEffect, useState } from 'react'
import { authorizedFetch } from '@/lib/api'
import type { ModuleType } from '@/lib/moduleRegistry'

export interface ModuleAccessState {
  isActive: boolean
  loading: boolean
  error: string | null
  savingsData?: {
    savingsZar: number
    savingsPercent: number
    savingsKwh: number
    confidence: number
    description: string
  }
}

/**
 * Check if a module is active for the current site and fetch related savings data.
 * 
 * @param module - Module type to check (e.g., 'control', 'maintenance', 'solar')
 * @returns Module access state with activation status and relevant savings data
 * 
 * @example
 * const { isActive, savingsData } = useModuleAccess('control')
 * if (!isActive && savingsData) {
 *   show upgrade prompt: `Save R${savingsData.savingsZar}/month`
 * }
 */
export function useModuleAccess(module: ModuleType | string): ModuleAccessState {
  const [state, setState] = useState<ModuleAccessState>({
    isActive: false,
    loading: true,
    error: null,
    savingsData: undefined,
  })

  useEffect(() => {
    const checkModuleAccess = async () => {
      try {
        // Get site ID from session storage
        const siteId = sessionStorage.getItem('sentinel_selected_site') || 'site-002'

        // Check if module is active
        const moduleResponse = await authorizedFetch(`/api/modules/status/${siteId}`)
        if (!moduleResponse.ok) {
          throw new Error('Failed to fetch module status')
        }

        const modules = await moduleResponse.json()
        const moduleActive = modules.some(
          (m: any) => m.module_type === module && m.status === 'active'
        )

        setState(prev => ({ ...prev, isActive: moduleActive }))

        // If module is not active, fetch relevant recommendation data for the upgrade prompt
        if (!moduleActive) {
          try {
            // Fetch recommendations to get savings data for this module
            const recResponse = await authorizedFetch(`/api/recommendations?module=${module}&site_id=${siteId}`)
            if (recResponse.ok) {
              const recommendations = await recResponse.json()

              // Find the most relevant/highest-impact recommendation for this module
              if (recommendations && recommendations.length > 0) {
                const topRecommendation = recommendations[0] // Sorted by impact
                
                setState(prev => ({
                  ...prev,
                  savingsData: {
                    savingsZar: topRecommendation.estimated_savings_zar || 0,
                    savingsPercent: topRecommendation.estimated_savings_percent || 0,
                    savingsKwh: topRecommendation.estimated_savings_kwh || 0,
                    confidence: topRecommendation.confidence || 0,
                    description: topRecommendation.description || '',
                  },
                }))
              }
            }
          } catch (err) {
            // Silently fail on recommendations fetch; module check is primary
            console.debug('Failed to fetch recommendations:', err)
          }
        }

        setState(prev => ({ ...prev, loading: false, error: null }))
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Unknown error'
        setState(prev => ({
          ...prev,
          loading: false,
          error: errorMessage,
          isActive: false, // Fail closed: assume module is inactive on error
        }))
      }
    }

    checkModuleAccess()
  }, [module])

  return state
}

/**
 * Module-to-description mapping for upgrade prompts.
 * Used by LockedFeatureOverlay to provide context-specific messages.
 */
export const MODULE_DESCRIPTIONS: Record<string, string> = {
  control: 'Controls module',
  maintenance: 'Maintenance module',
  solar: 'Solar module',
  lighting: 'Lighting module',
  dali: 'DALI module',
  ml: 'AI & Predictions module',
  energy: 'Energy module',
  security: 'Security module',
  hvac: 'HVAC module',
  water: 'Water management module',
  fire: 'Fire safety module',
}
