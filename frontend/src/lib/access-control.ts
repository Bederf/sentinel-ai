/**
 * Access Control - Company and User-Based Restrictions
 *
 * Manages view/module visibility based on user email domain and company.
 * Used to provide restricted demo experiences for specific clients.
 *
 * Two layers of access control:
 * 1. COMPANY_DEMO_CONFIGS: Domain-based restrictions (e.g., wardew.co.za)
 * 2. USER_DEMO_CONFIGS: Exact email-based restrictions (e.g., bederf@protonmail.com)
 *
 * Priority: USER_DEMO_CONFIGS > COMPANY_DEMO_CONFIGS > unrestricted
 */

import type { View } from './navigation';

/**
 * Per-user demo configurations.
 * Takes priority over company/domain-based configs.
 * Use this for generic email domains (gmail, protonmail, etc.) where
 * domain-based matching would be too broad.
 */
export const USER_DEMO_CONFIGS: Record<string, CompanyDemoConfig> = {
  'bederf@protonmail.com': {
    companyName: 'Bederf Solar Demo',
    demoFocus: 'solar-bess',
    allowedViews: [
      'dashboard',           // Base: always visible
      'digital-twin',        // Base: always visible
      'integrations',        // Base: System Health
      'solar',               // Add-on: Solar & BESS (their module)
      'control',             // Add-on: Building Controls (needed for solar control)
      'technician',          // Add-on: Tech Chat (base hvac module)
      'fleet',               // Add-on: Fleet ML (base ml module)
      'settings',            // Internal: password-protected module management
    ],
    defaultView: 'dashboard',
    viewMode: 'operator',
    description: 'Solar & BESS Demo for Bederf',
  },
};

/**
 * Company demo configurations.
 * Restricts views available to users from specific companies.
 * Does NOT apply if the user has a USER_DEMO_CONFIG entry.
 */
export const COMPANY_DEMO_CONFIGS: Record<string, CompanyDemoConfig> = {
  'wardew.co.za': {
    companyName: 'Wardew',
    demoFocus: 'dali-lighting',
    allowedViews: [
      'dashboard',           // Base: always visible
      'digital-twin',        // Base: always visible
      'integrations',        // Base: System Health
      'occupancy',           // Add-on: Occupancy monitoring (lighting module)
      'lighting',            // Add-on: Lighting control (lighting module)
      'control',             // Add-on: Building Controls (needed for lighting control)
      'technician',          // Add-on: Tech Chat (base hvac module)
      'fleet',               // Add-on: Fleet ML (base ml module)
      'settings',            // Internal: password-protected module management
    ],
    defaultView: 'occupancy',
    viewMode: 'operator',   // Changed from 'auditor' — Grant needs to demo controls
    description: 'DALI Lighting & Occupancy Control Demo',
  },
};

export interface CompanyDemoConfig {
  companyName: string;
  demoFocus: string;
  allowedViews: View[];
  defaultView: View;
  viewMode: 'auditor' | 'operator' | 'admin';
  description: string;
}

/**
 * Get demo config for a user — checks exact email first, then domain.
 * Returns config if user has a demo configuration, null otherwise.
 */
export function getCompanyDemoConfig(email: string): CompanyDemoConfig | null {
  const normalised = email.toLowerCase().trim();

  // 1. Check exact email match first (takes priority)
  if (USER_DEMO_CONFIGS[normalised]) {
    return USER_DEMO_CONFIGS[normalised];
  }

  // 2. Fall back to domain-based match
  const domain = normalised.split('@')[1];
  if (!domain) return null;

  return COMPANY_DEMO_CONFIGS[domain] || null;
}

/**
 * Check if user should have restricted access based on company.
 */
export function isRestrictedDemoUser(email: string): boolean {
  return getCompanyDemoConfig(email) !== null;
}

/**
 * Get allowed views for a user based on their email/company.
 * Returns all views if user is not from a restricted company.
 */
export function getAllowedViews(email: string, allViews: View[]): View[] {
  const config = getCompanyDemoConfig(email);
  if (!config) return allViews;

  // Filter to only allowed views from the config
  return allViews.filter(view => config.allowedViews.includes(view));
}

/**
 * Get the view mode (access level) for a user.
 * Used to determine if user can control devices or only view.
 */
export function getUserViewMode(email: string): 'auditor' | 'operator' | 'admin' {
  const config = getCompanyDemoConfig(email);
  return config?.viewMode || 'operator';
}

/**
 * Get the default view to show when user logs in.
 * DEFAULT LANDING PAGE: 'dashboard' (not AI Chat)
 *
 * Wardew (wardew.co.za) users override this and default to 'occupancy'.
 * Bederf protonmail users default to 'dashboard'.
 * All other users default to 'dashboard'.
 */
export function getDefaultView(email: string): View {
  const config = getCompanyDemoConfig(email);
  return config?.defaultView || 'dashboard';
}

/**
 * Check if user can access a specific view.
 */
export function canAccessView(email: string, view: View, allViews: View[]): boolean {
  const allowed = getAllowedViews(email, allViews);
  return allowed.includes(view);
}

/**
 * Check if user can control devices (non-auditor mode).
 */
export function canControlDevices(email: string): boolean {
  const mode = getUserViewMode(email);
  return mode !== 'auditor';
}
