/**
 * AIDisclosureBadge Component - EU AI Act Article 50 Transparency Label
 *
 * Reusable disclosure badge indicating AI-generated content.
 * Used across all components that display AI-generated outputs
 * to comply with Article 50 transparency requirements.
 *
 * Variants:
 * - "badge"  : Small inline "AI" pill (for cards, list items)
 * - "label"  : Longer text label (for panels, modals)
 * - "footer" : Muted footer text (for chat messages, detail views)
 */

interface AIDisclosureBadgeProps {
  /** Display variant */
  variant?: "badge" | "label" | "footer";
  /** Additional CSS class names */
  className?: string;
}

export function AIDisclosureBadge({
  variant = "badge",
  className = "",
}: AIDisclosureBadgeProps) {
  if (variant === "footer") {
    return (
      <p
        className={`text-xs mt-2 ${className}`}
        style={{ color: "var(--color-sentinel-text-secondary, #8e8e8e)", opacity: 0.7 }}
      >
        AI-generated &middot; Review before acting
      </p>
    );
  }

  if (variant === "label") {
    return (
      <span
        className={`text-xs italic ${className}`}
        style={{ color: "var(--color-sentinel-text-secondary, #9ca3af)" }}
      >
        AI-generated &middot; Review before acting
      </span>
    );
  }

  // Default: "badge"
  return (
    <span
      className={`text-xs font-medium px-1.5 py-0.5 rounded bg-sky-900/30 text-sky-300 border border-sky-800/40 ${className}`}
    >
      AI
    </span>
  );
}

export default AIDisclosureBadge;
