/**
 * Panel — shared panel container.
 *
 * Renders background: var(--color-sentinel-bg-panel) + border + radius.
 * Optional header row with icon (tinted by accentColor) + title + actions slot.
 *
 * Usage:
 *   <Panel>content</Panel>
 *   <Panel header={{ icon: <Shield />, title: "ESG Scores", actions: <Button /> }}>
 *     body
 *   </Panel>
 */

import type { ReactNode, CSSProperties } from "react";

interface PanelProps {
  children: ReactNode;
  /** Optional header row */
  header?: {
    icon?: ReactNode;
    title: string;
    actions?: ReactNode;
    /** CSS color for icon tint, default amber */
    accentColor?: string;
  };
  className?: string;
  style?: CSSProperties;
}

export function Panel({ children, header, className = "", style }: PanelProps) {
  return (
    <div
      className={className}
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
        borderRadius: 8,
        ...style,
      }}
    >
      {header && (
        <div
          className="px-4 py-2.5 flex items-center gap-2 text-sm font-semibold"
          style={{
            borderBottom: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-primary)",
          }}
        >
          {header.icon && (
            <span style={{ color: header.accentColor ?? "var(--color-sentinel-amber)" }}>
              {header.icon}
            </span>
          )}
          <span style={{ flex: 1 }}>{header.title}</span>
          {header.actions && <span style={{ flex: "none" }}>{header.actions}</span>}
        </div>
      )}
      <div>{children}</div>
    </div>
  );
}

export default Panel;
