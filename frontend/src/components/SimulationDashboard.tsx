/**
 * Simulation Tab — What-if Scenario Modelling (Coming Soon)
 *
 * Reserved for future what-if scenario modelling capability.
 * Gated behind the `simulation` add-on module.
 *
 * Previous contents have been split into:
 * - DataSourceTab → SIMBIOT page (admin-only simulator driver)
 * - AIPerformanceTab → System Health page (optimization analytics)
 * - ModelHealthTab → System Health page (ML model monitoring)
 */

import { Beaker } from "lucide-react";

export function SimulationDashboard() {
  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      <div
        className="glass-panel rounded-lg p-5 mb-6"
        style={{ border: "1px solid var(--glass-border)" }}
      >
        <h2
          className="text-lg font-semibold"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          Simulation
        </h2>
        <p
          className="text-sm mt-1"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          What-if scenario modelling
        </p>
      </div>

      <div
        className="rounded-lg p-12 text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <Beaker
          className="h-12 w-12 mx-auto mb-4"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        />
        <h3
          className="text-base font-semibold mb-2"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          What-if Scenario Modelling
        </h3>
        <p
          className="text-sm max-w-md mx-auto"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Run what-if scenarios to evaluate the impact of operational changes
          before applying them to your building. Compare energy profiles,
          maintenance strategies, and comfort trade-offs.
        </p>
        <p
          className="text-xs mt-4"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          Coming soon
        </p>
      </div>
    </div>
  );
}
