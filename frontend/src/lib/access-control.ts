/**
 * Access Control — Role-Based View Access
 *
 * Server-driven module access. No hardcoded per-user or per-company restrictions.
 * All views are available based on the user's role from the JWT token.
 */

import type { View } from './navigation';

/**
 * Get allowed views for a user based on their role.
 * All authenticated users see all views — server enforces module gating.
 */
export function getAllowedViews(_email: string, allViews: View[]): View[] {
  return allViews;
}

/**
 * Get the default view to show when user logs in.
 */
export function getDefaultView(_email: string): View {
  return 'dashboard';
}

/**
 * Check if user can access a specific view.
 */
export function canAccessView(_email: string, view: View, allViews: View[]): boolean {
  return allViews.includes(view);
}

/**
 * Check if user can control devices.
 * Role-based: operator and admin can control; auditor and developer cannot.
 */
export function canControlDevices(_email: string, role?: string): boolean {
  if (!role) return false;
  return role === 'operator' || role === 'admin';
}

/**
 * Check if user should have restricted access.
 * Always returns false — no hardcoded restrictions.
 */
export function isRestrictedDemoUser(_email: string): boolean {
  return false;
}

/**
 * Get user view mode from role.
 */
export function getUserViewMode(_email: string, role?: string): 'auditor' | 'operator' | 'admin' {
  if (role === 'admin') return 'admin';
  if (role === 'operator') return 'operator';
  return 'auditor';
}
