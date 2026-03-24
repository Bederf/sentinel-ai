/**
 * Equipment Type Instruction Registry
 *
 * Defines equipment-specific command and verification templates for advisory mode.
 * Each equipment type provides guidance on how to execute and verify control actions in the BMS.
 */

export interface EquipmentInstructions {
  type: string
  commandTemplate: (assetId: string, _actionSummary: string) => string
  verificationTemplate: (_assetId: string, primaryMetric: string) => string
  description: string
}

/**
 * Registry of equipment-specific instructions
 *
 * Each entry provides templates for command and verification text that is
 * equipment-specific and helps operators execute actions correctly.
 */
export const EQUIPMENT_TYPE_REGISTRY: Record<string, EquipmentInstructions> = {
  CHILLER: {
    type: 'CHILLER',
    commandTemplate: (assetId, _action) => {
      if (_action.toLowerCase().includes('backup') || _action.toLowerCase().includes('standby')) {
        return `Enable the standby chiller sequence for ${assetId} and transfer load to the backup machine.`
      }
      return `Adjust the chilled-water setpoint for ${assetId} to the recommended target and confirm the point writes successfully.`
    },
    verificationTemplate: (_assetId, primaryMetric) =>
      `Verify chilled-water temperatures stabilise, the active alarm clears, and ${primaryMetric.toLowerCase()} extends rather than contracts.`,
    description: 'Chiller plant equipment',
  },

  AHU: {
    type: 'AHU',
    commandTemplate: (assetId, _action) =>
      `Open the AHU controls for ${assetId} and apply the recommended supply-air, damper, or fan adjustment.`,
    verificationTemplate: (_assetId, primaryMetric) =>
      `Verify zone conditions move back toward target and ${primaryMetric.toLowerCase()} improves on the next telemetry refresh.`,
    description: 'Air Handling Unit',
  },

  FCU: {
    type: 'FCU',
    commandTemplate: (assetId, _action) =>
      `Open the zone controls for ${assetId} (Fan Coil Unit) and apply the recommended comfort correction (fan speed, heating, or cooling valve).`,
    verificationTemplate: (_assetId, primaryMetric) =>
      `Verify zone conditions move back toward target and ${primaryMetric.toLowerCase()} improves on the next telemetry refresh.`,
    description: 'Fan Coil Unit',
  },

  VAV: {
    type: 'VAV',
    commandTemplate: (assetId, _action) =>
      `Open the zone controls for ${assetId} (Variable Air Volume) and apply the recommended comfort correction (airflow, heating, or cooling).`,
    verificationTemplate: (_assetId, primaryMetric) =>
      `Verify zone conditions move back toward target and ${primaryMetric.toLowerCase()} improves on the next telemetry refresh.`,
    description: 'Variable Air Volume terminal',
  },

  PUMP: {
    type: 'PUMP',
    commandTemplate: (assetId, _action) =>
      `Command the affected pump sequence for ${assetId} and confirm the duty or enable state changes as intended.`,
    verificationTemplate: (_assetId, primaryMetric) =>
      `Verify the pump operates at the correct duty point and ${primaryMetric.toLowerCase()} does not worsen.`,
    description: 'Circulation pump',
  },

  UPS: {
    type: 'UPS',
    commandTemplate: (assetId, _action) =>
      `Open the critical power controls for ${assetId} (UPS) and apply the recommended operating mode or battery transfer command.`,
    verificationTemplate: (_assetId, _primaryMetric) =>
      `Verify the power asset remains available and no new transfer or battery alarms appear after the change.`,
    description: 'Uninterruptible Power Supply',
  },

  GEN: {
    type: 'GEN',
    commandTemplate: (assetId, _action) =>
      `Open the critical power controls for ${assetId} (Generator) and apply the recommended operating mode or transfer command.`,
    verificationTemplate: (_assetId, _primaryMetric) =>
      `Verify the generator remains ready and no new transfer or fuel alarms appear after the change.`,
    description: 'Generator set',
  },

  DALI: {
    type: 'DALI',
    commandTemplate: (assetId, _action) =>
      `Open the lighting controls for ${assetId} and apply the recommended scene or level override (e.g., emergency lighting, preset scenes).`,
    verificationTemplate: (_assetId, primaryMetric) =>
      `Verify lighting responds correctly and ${primaryMetric.toLowerCase()} does not worsen.`,
    description: 'DALI lighting ballast',
  },

  LUM: {
    type: 'LUM',
    commandTemplate: (assetId, _action) =>
      `Open the lighting controls for ${assetId} and apply the recommended scene or level override.`,
    verificationTemplate: (_assetId, primaryMetric) =>
      `Verify lighting responds correctly and ${primaryMetric.toLowerCase()} does not worsen.`,
    description: 'Luminaire (lighting fixture)',
  },

  CT: {
    type: 'CT',
    commandTemplate: (assetId, _action) =>
      `Monitor the current load on ${assetId} (Current Transformer / electrical monitoring point). If rebalancing is needed, escalate to the electrician for manual balancing.`,
    verificationTemplate: (_assetId, _primaryMetric) =>
      `Verify load is balanced and no overload alarms persist. Escalate to electrician if action required.`,
    description: 'Current Transformer (electrical monitoring)',
  },

  FIRE: {
    type: 'FIRE',
    commandTemplate: (assetId, _action) =>
      `Verify fire safety system interlocks for ${assetId}. Safety actions (dampers, doors, pressurization) are typically automatic. Escalate immediately to FM/Safety team if manual intervention is required.`,
    verificationTemplate: (_assetId, _primaryMetric) =>
      `Verify fire safety interlocks are operational. Do NOT override without FM authorization.`,
    description: 'Fire safety equipment',
  },

  ACC: {
    type: 'ACC',
    commandTemplate: (assetId, _action) =>
      `Review security access control status for ${assetId}. Coordinate with security team before making any changes to access control points.`,
    verificationTemplate: (_assetId, _primaryMetric) =>
      `Verify access control system is operational and log all changes for audit trail.`,
    description: 'Access Control (door locks, turnstiles)',
  },

  CCTV: {
    type: 'CCTV',
    commandTemplate: (assetId, _action) =>
      `Review CCTV system status for ${assetId}. Coordinate with security team if camera reset or repositioning is needed.`,
    verificationTemplate: (_assetId, _primaryMetric) =>
      `Verify camera feeds are operational and recording normally.`,
    description: 'CCTV camera',
  },

  MTR: {
    type: 'MTR',
    commandTemplate: (assetId, _action) =>
      `Verify meter reading for ${assetId}. Energy meters are read-only; no control action available. Review data for billing or anomaly detection.`,
    verificationTemplate: (_assetId, _primaryMetric) =>
      `Verify meter reading is available and data is consistent with expected consumption patterns.`,
    description: 'Energy/utility meter (read-only)',
  },

  UNKNOWN: {
    type: 'UNKNOWN',
    commandTemplate: (assetId, _action) =>
      `Open the control page for ${assetId} and apply the recommended action exactly as shown.`,
    verificationTemplate: (_assetId, primaryMetric) =>
      `Verify the commanded point holds, the recommendation outcome appears in telemetry, and ${primaryMetric.toLowerCase()} does not worsen.`,
    description: 'Unknown equipment type',
  },
}

/**
 * Get equipment-specific instructions for a given type
 *
 * @param type - The equipment type (e.g., 'CHILLER', 'AHU', null for unknown)
 * @returns Equipment instructions including command and verification templates
 */
export function getEquipmentInstructions(type: string | null | undefined): EquipmentInstructions {
  if (!type) {
    return EQUIPMENT_TYPE_REGISTRY.UNKNOWN
  }

  // Try exact match first
  const uppercase = type.toUpperCase()
  if (uppercase in EQUIPMENT_TYPE_REGISTRY) {
    return EQUIPMENT_TYPE_REGISTRY[uppercase]
  }

  // Try partial match for compound types (e.g., 'FCU/VAV' → 'FCU')
  if (uppercase.includes('/')) {
    const parts = uppercase.split('/')
    for (const part of parts) {
      if (part.trim() in EQUIPMENT_TYPE_REGISTRY) {
        return EQUIPMENT_TYPE_REGISTRY[part.trim()]
      }
    }
  }

  // Return UNKNOWN fallback
  return EQUIPMENT_TYPE_REGISTRY.UNKNOWN
}
