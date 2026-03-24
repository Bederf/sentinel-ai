/**
 * BMS Navigation Mapping Registry
 *
 * Defines site-specific navigation paths for the advisory execution layer.
 * This allows different sites to have different BMS hierarchies while maintaining
 * a consistent contract for decision surface rendering.
 */

export interface BmsNavigationRoot {
  site: string
  navigationRoot: string[]
  description: string
}

/**
 * Registry of site-specific BMS navigation roots
 *
 * Each entry maps a site prefix to the navigation hierarchy used in that BMS.
 * The array represents the breadcrumb path operators follow to reach control points.
 */
export const BMS_NAVIGATION_REGISTRY: Record<string, BmsNavigationRoot> = {
  S002: {
    site: 'S002',
    navigationRoot: ['Desigo CC', 'Site-002', 'Plant Controls'],
    description: 'Siemens Desigo CC with Site-002 configuration',
  },
  // Add additional sites as they are onboarded
  // S001: { ... }
  // S003: { ... }
}

/**
 * Get the BMS navigation root for a given site
 *
 * @param site - The site prefix (e.g., 'S002', 'site-001', or null for unknown)
 * @returns Navigation root array for the site, or fallback if not found
 */
export function getBmsNavigationRoot(site: string | null | undefined): string[] {
  if (!site) {
    return getFallbackNavigationRoot()
  }

  // Try exact match first (e.g., 'S002')
  const registry = BMS_NAVIGATION_REGISTRY[site]
  if (registry) {
    return registry.navigationRoot
  }

  // Try uppercase conversion (e.g., 'site-002' → 'SITE-002')
  const uppercase = site.toUpperCase()
  const uppercaseRegistry = BMS_NAVIGATION_REGISTRY[uppercase]
  if (uppercaseRegistry) {
    return uppercaseRegistry.navigationRoot
  }

  // Return fallback for unknown sites
  return getFallbackNavigationRoot()
}

/**
 * Fallback navigation root for sites not in the registry
 * Used for new sites before their specific BMS hierarchy is configured
 */
function getFallbackNavigationRoot(): string[] {
  return ['BMS', 'Operations', 'Asset Controls']
}

/**
 * Get a human-readable description of the BMS navigation for a site
 *
 * @param site - The site prefix
 * @returns Description string for logging/debugging
 */
export function describeBmsNavigation(site: string | null | undefined): string {
  if (!site) {
    return 'BMS (fallback, unknown site)'
  }

  const registry = BMS_NAVIGATION_REGISTRY[site]
  if (registry) {
    return `${registry.description} (${site})`
  }

  const uppercase = site.toUpperCase()
  const uppercaseRegistry = BMS_NAVIGATION_REGISTRY[uppercase]
  if (uppercaseRegistry) {
    return `${uppercaseRegistry.description} (${uppercase})`
  }

  return `BMS (fallback, ${site} not in registry)`
}
