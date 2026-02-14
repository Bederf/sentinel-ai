/**
 * Solar Configuration API Client
 *
 * Provides type-safe API methods for solar site configuration management,
 * including plants, inverters, BESS, and grid meter setup.
 */

import { fetchApi } from "./client";

// ============================================================================
// Type Definitions
// ============================================================================

export interface SolarPlant {
  plant_id: string;
  name: string;
  capacity_kwp: number;
  panel_model?: string;
  panel_count: number;
  commissioning_date?: string;
}

export interface SolarInverter {
  equipment_id: string;
  manufacturer: string;
  model: string;
  rated_kva: number;
  modbus_ip: string;
  modbus_port?: number;
  modbus_unit_id?: number;
}

export interface BESSConfig {
  equipment_id: string;
  manufacturer: string;
  model: string;
  capacity_kwh: number;
  rated_power_kw: number;
  modbus_ip: string;
  modbus_port?: number;
  modbus_unit_id?: number;
}

export interface GridMeterConfig {
  equipment_id: string;
  manufacturer: string;
  modbus_ip: string;
  modbus_port?: number;
  modbus_unit_id?: number;
}

export interface SolarConfig {
  plants: SolarPlant[];
  inverters: Record<string, SolarInverter[]>;
  bess?: BESSConfig;
  grid_meter?: GridMeterConfig;
  utility?: string;
  tariff?: string;
}

export interface SolarSiteRequest {
  site_id: string;
  site_name: string;
  latitude: number;
  longitude: number;
  config: SolarConfig;
}

export interface SolarSiteResponse {
  status: string;
  site_id: string;
  message?: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  message: string;
}

// ============================================================================
// API Methods
// ============================================================================

export const solarConfigApi = {
  /**
   * Create a new solar site configuration and activate the Solar module.
   *
   * @param request - Solar site configuration with plants, inverters, BESS, meters
   * @returns Success response with site ID
   */
  createSolarSite: (request: SolarSiteRequest): Promise<SolarSiteResponse> =>
    fetchApi<SolarSiteResponse>("/api/solar-config/sites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }),

  /**
   * Retrieve existing solar configuration for editing.
   *
   * @param siteId - Site ID to retrieve configuration for
   * @returns Solar configuration for the site
   */
  getSolarConfig: (siteId: string): Promise<SolarConfig> =>
    fetchApi<SolarConfig>(`/api/solar-config/sites/${siteId}`),

  /**
   * Validate solar configuration without saving.
   *
   * @param request - Solar site configuration to validate
   * @returns Validation result with errors (if any)
   */
  validateConfig: (request: SolarSiteRequest): Promise<ValidationResult> =>
    fetchApi<ValidationResult>("/api/solar-config/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }),
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Validate equipment code format.
 *
 * @param code - Equipment code (e.g., S002-INV-R-001)
 * @returns True if code format is valid
 */
export function isValidEquipmentCode(code: string): boolean {
  // Pattern: S{3digits}-{type}-{location}-{sequence or identifier}
  // Location: Letters and/or digits (e.g., R, B1, L2, G)
  // Sequence/ID: Either 3 digits (e.g., 001) or text identifier (e.g., GRID)
  const pattern = /^S\d{3}-[A-Z]+-[A-Z0-9]{1,2}-(?:\d{3}|[A-Z]+)$/;
  return pattern.test(code);
}

/**
 * Calculate inverter coverage percentage for a plant.
 *
 * @param capacityKwp - Plant capacity in kWp
 * @param inverters - List of inverters
 * @returns Coverage object with percentage and warning if needed
 */
export function calculateInverterCoverage(
  capacityKwp: number,
  inverters: SolarInverter[]
): { coverage_pct: number; warning?: string } {
  const totalKva = inverters.reduce((sum, inv) => sum + inv.rated_kva, 0);
  const coveragePct = (totalKva / capacityKwp) * 100;

  const result: { coverage_pct: number; warning?: string } = {
    coverage_pct: coveragePct,
  };

  if (coveragePct < 80) {
    result.warning = `Coverage ${coveragePct.toFixed(1)}% < 80% (recommend >80%)`;
  }

  return result;
}

/**
 * Generate equipment ID suggestion based on site and type.
 *
 * @param siteId - Site ID (e.g., S002)
 * @param type - Equipment type (INV, BESS, MTR)
 * @param location - Location code (R, B1, etc.)
 * @param sequence - Sequence number
 * @returns Suggested equipment ID
 */
export function suggestEquipmentId(
  siteId: string,
  type: string,
  location: string,
  sequence: number
): string {
  const siteCode = siteId.replace("site-", "S");
  return `${siteCode}-${type}-${location}-${String(sequence).padStart(3, "0")}`;
}
