/**
 * Time formatting utilities for SENTINEL BMS
 * All times displayed in 24-hour format (HH:MM)
 */

/**
 * Format time to 24-hour format (HH:MM)
 * @param date - Date object or ISO string
 * @returns Formatted time string (e.g., "14:30", "23:45")
 */
export function formatTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleTimeString('en-ZA', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/**
 * Format date and time to 24-hour format
 * @param date - Date object or ISO string
 * @returns Formatted date and time string (e.g., "30 Jan 2026, 14:30")
 */
export function formatDateTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleString('en-ZA', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/**
 * Format relative time in human-readable format
 * @param timestamp - ISO timestamp string
 * @returns Relative time string (e.g., "5 minutes ago", "2 hours ago", "Just now")
 */
export function formatRelativeTime(timestamp: string | null): string {
  if (!timestamp) return 'Never';

  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now.getTime() - then.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 2) return 'Just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

  // Older than 7 days, show the date
  return then.toLocaleDateString('en-ZA', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

/**
 * Format date only (without time)
 * @param date - Date object or ISO string
 * @returns Formatted date string (e.g., "30 Jan 2026")
 */
export function formatDate(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleDateString('en-ZA', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

/**
 * Get the user's local timezone
 * @returns IANA timezone string (e.g., "Africa/Johannesburg", "Europe/London")
 */
export function getUserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/**
 * Get timezone abbreviation (e.g., "SAST", "UTC", "GMT")
 * @param timezone - IANA timezone string
 * @returns Short timezone abbreviation
 */
export function getTimezoneAbbreviation(timezone: string): string {
  // Map of common IANA timezones to their abbreviations
  const tzMap: Record<string, string> = {
    'Africa/Johannesburg': 'SAST',
    'Europe/London': 'GMT',
    'America/New_York': 'EST',
    'America/Los_Angeles': 'PST',
    'Asia/Dubai': 'GST',
    'Asia/Singapore': 'SGT',
    'Australia/Sydney': 'AEST',
    'UTC': 'UTC',
  };

  if (tzMap[timezone]) {
    return tzMap[timezone];
  }

  // Fallback: extract from formatted date
  try {
    const date = new Date();
    const formatter = new Intl.DateTimeFormat('en', {
      timeZone: timezone,
      timeZoneName: 'short',
    });
    const parts = formatter.formatToParts(date);
    const tzPart = parts.find(p => p.type === 'timeZoneName');
    return tzPart?.value || timezone.split('/').pop() || 'UTC';
  } catch {
    return timezone.split('/').pop() || 'UTC';
  }
}

/**
 * Check if a building's timezone differs from the user's local timezone
 * @param buildingTimezone - IANA timezone of the building
 * @returns true if timezones are different
 */
export function isDifferentTimezone(buildingTimezone: string | undefined): boolean {
  if (!buildingTimezone) return false;
  const userTz = getUserTimezone();
  return buildingTimezone !== userTz;
}

/**
 * Get the UTC offset for a timezone
 * @param timezone - IANA timezone string
 * @returns UTC offset string (e.g., "+02:00", "-05:00")
 */
export function getTimezoneOffset(timezone: string): string {
  try {
    const date = new Date();
    const formatter = new Intl.DateTimeFormat('en', {
      timeZone: timezone,
      timeZoneName: 'longOffset',
    });
    const parts = formatter.formatToParts(date);
    const offsetPart = parts.find(p => p.type === 'timeZoneName');
    // Extract just the offset part (e.g., "GMT+2" -> "+02:00")
    const match = offsetPart?.value.match(/GMT([+-]\d+)/);
    if (match) {
      const hours = parseInt(match[1], 10);
      const sign = hours >= 0 ? '+' : '-';
      return `${sign}${String(Math.abs(hours)).padStart(2, '0')}:00`;
    }
    return '+00:00';
  } catch {
    return '+00:00';
  }
}

/**
 * Format time in a specific timezone with optional timezone indicator
 * @param timeStr - Time string in HH:MM format (e.g., "07:00")
 * @param timezone - IANA timezone string
 * @param showTz - Whether to show timezone abbreviation
 * @returns Formatted time with optional timezone (e.g., "07:00 SAST")
 */
export function formatTimeWithTimezone(
  timeStr: string,
  timezone?: string,
  showTz: boolean = false
): string {
  if (!showTz || !timezone) return timeStr;
  const tzAbbr = getTimezoneAbbreviation(timezone);
  return `${timeStr} ${tzAbbr}`;
}

/**
 * Get current time in a specific timezone
 * @param timezone - IANA timezone string
 * @returns Current time in HH:MM format
 */
export function getCurrentTimeInTimezone(timezone: string): string {
  const now = new Date();
  return now.toLocaleTimeString('en-ZA', {
    timeZone: timezone,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}
