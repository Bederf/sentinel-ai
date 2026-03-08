import { useState, useRef, useEffect } from "react";
import { useTheme, THEME_IDS, THEMES } from "../contexts/ThemeContext";

/**
 * ThemeSwitcher — compact dropdown for the header bar.
 * Shows current theme icon + label, opens a dropdown with swatches.
 *
 * Usage:
 *   <ThemeSwitcher />
 */
export function ThemeSwitcher() {
  const { theme, themeConfig, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      {/* Trigger button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 px-2 py-1 rounded transition-colors hover:brightness-110"
        style={{
          background: open
            ? "var(--color-sentinel-bg-panel)"
            : "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
        }}
        aria-label="Switch theme"
        title={`Theme: ${themeConfig.label}`}
      >
        {/* Accent swatch */}
        <span
          className="w-3 h-3 rounded-full"
          style={{
            background: themeConfig.accentColor,
            boxShadow: `0 0 6px ${themeConfig.accentColor}60`,
          }}
        />
        <span
          className="text-xs font-medium hidden sm:inline"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {themeConfig.label}
        </span>
        {/* Chevron */}
        <svg
          className="w-3 h-3 transition-transform"
          style={{
            color: "var(--color-sentinel-text-disabled)",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
          }}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div
          className="absolute top-full right-0 mt-2 w-64 rounded-md shadow-lg z-50 overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Header */}
          <div
            className="px-3 py-2"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <span
              className="text-xs font-medium uppercase tracking-wider"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Dashboard Theme
            </span>
          </div>

          {/* Theme options */}
          <div className="py-1">
            {THEME_IDS.map((id) => {
              const t = THEMES[id];
              const isActive = theme === id;
              return (
                <button
                  key={id}
                  onClick={() => {
                    setTheme(id);
                    setOpen(false);
                  }}
                  className="w-full flex items-center gap-3 px-3 py-2.5 transition-colors text-left"
                  style={{
                    background: isActive
                      ? `${t.accentColor}12`
                      : "transparent",
                    borderLeft: isActive
                      ? `3px solid ${t.accentColor}`
                      : "3px solid transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      (e.currentTarget as HTMLElement).style.background =
                        "rgba(255,255,255,0.03)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      (e.currentTarget as HTMLElement).style.background =
                        "transparent";
                    }
                  }}
                >
                  {/* Swatch + icon */}
                  <span
                    className="w-5 h-5 rounded flex items-center justify-center text-xs"
                    style={{
                      background: `${t.accentColor}20`,
                      border: `1px solid ${t.accentColor}40`,
                    }}
                  >
                    {t.icon}
                  </span>

                  {/* Label + description */}
                  <div className="flex-1 min-w-0">
                    <div
                      className="text-sm font-medium"
                      style={{
                        color: isActive
                          ? t.accentColor
                          : "var(--color-sentinel-text-primary)",
                      }}
                    >
                      {t.label}
                    </div>
                    <div
                      className="text-xs truncate"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    >
                      {t.description}
                    </div>
                  </div>

                  {/* Active check */}
                  {isActive && (
                    <svg
                      className="w-4 h-4 flex-none"
                      style={{ color: t.accentColor }}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2.5}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>

          {/* Footer hint */}
          <div
            className="px-3 py-2"
            style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
          >
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Theme is saved per browser
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
