/**
 * TabBar — shared tab navigation component.
 *
 * Used for both top-level page tabs (amber accent) and sub-domain
 * tabs within a page (blue accent). Pass `accentColor` to switch.
 *
 * Tabs can carry an optional count badge (e.g. compliance domain rows).
 */

import type { ReactNode, CSSProperties } from "react";

export interface TabDef {
  id: string;
  label: string;
  icon?: ReactNode;
  count?: number;
}

interface TabBarProps {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
  /** CSS color for the active underline + label + tinted background. */
  accentColor?: string;
  style?: CSSProperties;
}

export function TabBar({
  tabs,
  active,
  onChange,
  accentColor = "var(--color-sentinel-amber)",
  style,
}: TabBarProps) {
  return (
    <div
      style={{
        display: "flex",
        overflowX: "auto",
        borderBottom: "1px solid var(--color-sentinel-border)",
        msOverflowStyle: "none",
        scrollbarWidth: "none",
        ...style,
      }}
    >
      {tabs.map((tab) => {
        const isActive = active === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            style={{
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "10px 16px",
              fontSize: 13,
              fontWeight: isActive ? 600 : 500,
              cursor: "pointer",
              border: "none",
              borderBottom: `2px solid ${isActive ? accentColor : "transparent"}`,
              background: isActive ? `color-mix(in srgb, ${accentColor} 10%, transparent)` : "transparent",
              color: isActive ? accentColor : "var(--color-sentinel-text-secondary)",
              transition: "all 0.15s",
              whiteSpace: "nowrap",
            }}
            onMouseEnter={(e) => {
              if (!isActive) {
                e.currentTarget.style.color = "var(--color-sentinel-text-primary)";
                e.currentTarget.style.background = "rgba(255,255,255,0.03)";
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                e.currentTarget.style.color = "var(--color-sentinel-text-secondary)";
                e.currentTarget.style.background = "transparent";
              }
            }}
          >
            {tab.icon}
            <span>{tab.label}</span>
            {tab.count != null && (
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  padding: "1px 5px",
                  borderRadius: 10,
                  background: isActive
                    ? `color-mix(in srgb, ${accentColor} 22%, transparent)`
                    : "rgba(139,148,158,0.2)",
                  color: isActive ? accentColor : "var(--color-sentinel-text-secondary)",
                }}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export default TabBar;
