/**
 * Types for batch aggregator responses
 */

/**
 * Device safety status response
 */
export interface DeviceSafetyStatus {
  device_id: string;
  status: "safe" | "warning" | "blocked";
  rules_violated: Array<{
    rule_id: string;
    name: string;
    severity: string;
  }>;
}

/**
 * Device readings/status response
 */
export interface DeviceStatus {
  id: string;
  name: string;
  device_type: string;
  status: string;
  last_seen?: string;
  updated_at?: string;
}

/**
 * Device condition/health response
 */
export interface DeviceCondition {
  id: string;
  name: string;
  device_type: string;
  status: string;
  last_seen?: string;
  updated_at?: string;
  safety_status?: DeviceSafetyStatus;
}

/**
 * Batch response wrapper
 */
export interface BatchResponse<T> {
  results: Record<string, T>;
  errors: Record<string, string>;
}
