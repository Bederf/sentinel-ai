/**
 * Access Control - Company and User-Based Restrictions
 *
 * Manages view/module visibility based on user email domain and company.
 * Used to provide restricted demo experiences for specific clients.
 */

import type { View } from './navigation';

/**
 * Company demo configurations.
 * Restricts views available to users from specific companies.
 */
export const COMPANY_DEMO_CONFIGS: Record<string, CompanyDemoConfig> = {
  'wardew.co.za': {
    companyName: 'Wardew',
    demoFocus: 'desigo-tridonic',
    allowedViews: ['dashboard', 'chat', 'control', 'occupancy', 'digital-twin'],
    defaultView: 'dashboard',
    viewMode: 'auditor', // read-only
    description: 'Desigo-Tridonic Integration Demo',
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
 * Get company demo config from user email.
 * Returns config if user's email domain has a demo configuration, null otherwise.
 */
export function getCompanyDemoConfig(email: string): CompanyDemoConfig | null {
  const domain = email.toLowerCase().split('@')[1];
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

  // Filter to only allowed views
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
