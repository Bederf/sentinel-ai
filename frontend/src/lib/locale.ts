/**
 * South African Locale Configuration
 *
 * Provides localization utilities for South African English (en-ZA)
 * Supports currency (ZAR), date/time, numbers, and region-specific text.
 */

/**
 * Locale settings
 */
export const LOCALE = {
  code: 'en-ZA',
  name: 'South African English',
  country: 'South Africa',
  currency: 'ZAR',
  timezone: 'Africa/Johannesburg',
  dateFormat: 'DD MMM YYYY', // e.g., "15 Feb 2026"
  timeFormat: '24h', // 24-hour format
};

/**
 * Format currency with South African Rand
 * @param amount - Amount in ZAR
 * @param minimumFractionDigits - Minimum decimal places (default: 0)
 * @param maximumFractionDigits - Maximum decimal places (default: 0)
 * @returns Formatted currency string (e.g., "R1,234.56")
 */
export function formatCurrencyZAR(
  amount: number,
  minimumFractionDigits: number = 0,
  maximumFractionDigits: number = 0
): string {
  return new Intl.NumberFormat('en-ZA', {
    style: 'currency',
    currency: 'ZAR',
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(amount);
}

/**
 * Format large numbers with South African formatting
 * @param value - Number to format
 * @param minimumFractionDigits - Minimum decimal places (default: 0)
 * @param maximumFractionDigits - Maximum decimal places (default: 2)
 * @returns Formatted number string (e.g., "1 234,56")
 */
export function formatNumber(
  value: number,
  minimumFractionDigits: number = 0,
  maximumFractionDigits: number = 2
): string {
  return new Intl.NumberFormat('en-ZA', {
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(value);
}

/**
 * Format percentage with South African formatting
 * @param value - Percentage value (0-100)
 * @param decimalPlaces - Number of decimal places (default: 1)
 * @returns Formatted percentage string (e.g., "45,5%")
 */
export function formatPercentage(value: number, decimalPlaces: number = 1): string {
  const formatted = new Intl.NumberFormat('en-ZA', {
    minimumFractionDigits: decimalPlaces,
    maximumFractionDigits: decimalPlaces,
  }).format(value);
  return `${formatted}%`;
}

/**
 * Format energy consumption (kWh)
 * @param kwh - Energy value in kilowatt-hours
 * @returns Formatted energy string (e.g., "1 234,56 kWh")
 */
export function formatEnergy(kwh: number): string {
  if (kwh >= 1000000) {
    return `${formatNumber(kwh / 1000000, 0, 2)} MWh`;
  }
  if (kwh >= 1000) {
    return `${formatNumber(kwh / 1000, 0, 2)} kWh`;
  }
  return `${formatNumber(kwh, 0, 2)} Wh`;
}

/**
 * Format power (kW)
 * @param kw - Power value in kilowatts
 * @returns Formatted power string (e.g., "45,5 kW")
 */
export function formatPower(kw: number): string {
  if (kw >= 1000) {
    return `${formatNumber(kw / 1000, 0, 2)} MW`;
  }
  return `${formatNumber(kw, 0, 2)} kW`;
}

/**
 * Format CO2 emissions
 * @param kg - CO2 in kilograms
 * @returns Formatted emissions string (e.g., "1 234,56 kg CO₂")
 */
export function formatCO2(kg: number): string {
  if (kg >= 1000) {
    return `${formatNumber(kg / 1000, 0, 2)} t CO₂`;
  }
  return `${formatNumber(kg, 0, 2)} kg CO₂`;
}

/**
 * Format water consumption (litres)
 * @param litres - Water volume in litres
 * @returns Formatted water string (e.g., "1 234 l" or "1,23 m³")
 */
export function formatWater(litres: number): string {
  if (litres >= 1000) {
    return `${formatNumber(litres / 1000, 0, 2)} m³`;
  }
  return `${formatNumber(litres, 0, 0)} ℓ`;
}

/**
 * South African region/city names (for reference)
 */
export const REGIONS = {
  'Gauteng': 'Gauteng',
  'Western Cape': 'Western Cape',
  'KwaZulu-Natal': 'KwaZulu-Natal',
  'Limpopo': 'Limpopo',
  'Mpumalanga': 'Mpumalanga',
  'Free State': 'Free State',
  'Eastern Cape': 'Eastern Cape',
  'Northern Cape': 'Northern Cape',
  'North West': 'North West',
} as const;

/**
 * Major South African cities (for reference)
 */
export const CITIES = {
  'Johannesburg': 'Johannesburg',
  'Cape Town': 'Cape Town',
  'Durban': 'Durban',
  'Pretoria': 'Pretoria',
  'Bloemfontein': 'Bloemfontein',
  'Port Elizabeth': 'Port Elizabeth',
  'Pietermaritzburg': 'Pietermaritzburg',
  'East London': 'East London',
  'Tshwane': 'Tshwane',
  'eThekwini': 'eThekwini',
} as const;

/**
 * Day names in South African English
 */
export const DAY_NAMES = {
  short: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
  long: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
} as const;

/**
 * Month names in South African English
 */
export const MONTH_NAMES = {
  short: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
  long: [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ],
} as const;

/**
 * Get localized text for common UI labels
 */
export const UI_LABELS = {
  // Navigation
  dashboard: 'Dashboard',
  analytics: 'Analytics',
  settings: 'Settings',
  help: 'Help',

  // Common actions
  save: 'Save',
  cancel: 'Cancel',
  delete: 'Delete',
  edit: 'Edit',
  add: 'Add',
  create: 'Create',
  search: 'Search',
  filter: 'Filter',
  sort: 'Sort',
  export: 'Export',
  import: 'Import',

  // Energy terms
  energy: 'Energy',
  consumption: 'Consumption',
  savings: 'Savings',
  demand: 'Demand',
  generation: 'Generation',

  // Time periods
  today: 'Today',
  yesterday: 'Yesterday',
  week: 'Week',
  month: 'Month',
  year: 'Year',

  // Status
  online: 'Online',
  offline: 'Offline',
  active: 'Active',
  inactive: 'Inactive',
  warning: 'Warning',
  critical: 'Critical',
  normal: 'Normal',
} as const;
