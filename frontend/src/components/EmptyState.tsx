/**
 * EmptyState — canonical empty state pattern.
 *
 * Centered, muted, with a faded icon + title + optional subtext + CTA.
 * Used when a panel/tab has no data to display.
 */

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  /** Lucide icon component (pass the component, not a rendered node) */
  icon: LucideIcon;
  /** Bold one-liner title */
  title: string;
  /** Optional muted helper text below the title */
  subtext?: string;
  /** Optional CTA (button, link, etc.) */
  cta?: ReactNode;
}

export function EmptyState({ icon: Icon, title, subtext, cta }: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 p-8"
      style={{ textAlign: "center" }}
    >
      <Icon
        size={32}
        style={{ color: "var(--color-sentinel-text-disabled)", opacity: 0.6 }}
      />
      <div
        className="text-sm font-medium"
        style={{ color: "var(--color-sentinel-text-primary)" }}
      >
        {title}
      </div>
      {subtext && (
        <div
          className="text-xs"
          style={{ color: "var(--color-sentinel-text-secondary)", maxWidth: 280 }}
        >
          {subtext}
        </div>
      )}
      {cta && <div className="mt-1">{cta}</div>}
    </div>
  );
}

export default EmptyState;
