/**
 * IngestionModeBanner — Phase 108
 *
 * Prominent pill/badge showing the current ingestion mode.
 * Colors: amber (SHADOW_LIVE), red accent (LIVE_CONTROL).
 */

interface IngestionModeBannerProps {
  mode: string;
  isLive: boolean;
}

const MODE_STYLES: Record<string, { bg: string; border: string; accent: string; label: string }> = {
  shadow_live: {
    bg: 'rgba(245, 158, 11, 0.15)',
    border: 'rgba(245, 158, 11, 0.35)',
    accent: 'var(--color-sentinel-amber)',
    label: 'SHADOW LIVE',
  },
  live_control: {
    bg: 'rgba(220, 38, 38, 0.15)',
    border: 'rgba(220, 38, 38, 0.35)',
    accent: 'var(--color-sentinel-red)',
    label: 'LIVE CONTROL',
  },
};

export function IngestionModeBanner({ mode, isLive }: IngestionModeBannerProps) {
  const style = MODE_STYLES[mode] || MODE_STYLES.shadow_live;

  return (
    <div
      className="glass-panel rounded-lg p-4 flex items-center justify-between"
      style={{ border: `1px solid ${style.border}` }}
    >
      <div className="flex items-center gap-3">
        <span
          className="inline-block h-3 w-3 rounded-full"
          style={{ background: style.accent }}
        />
        <div>
          <span
            className="text-xs font-medium uppercase tracking-wider"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Ingestion Mode
          </span>
          <p
            className="text-lg font-semibold tracking-tight"
            style={{ color: style.accent }}
          >
            {style.label}
          </p>
        </div>
      </div>
      <span
        className="inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium"
        style={{
          background: isLive ? 'rgba(220, 38, 38, 0.15)' : 'rgba(16, 185, 129, 0.15)',
          border: `1px solid ${isLive ? 'rgba(220, 38, 38, 0.35)' : 'rgba(16, 185, 129, 0.35)'}`,
          color: isLive ? 'var(--color-sentinel-red)' : 'var(--color-sentinel-green)',
        }}
      >
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: isLive ? 'var(--color-sentinel-red)' : 'var(--color-sentinel-green)' }}
        />
        {isLive ? 'LIVE' : 'OFFLINE'}
      </span>
    </div>
  );
}

export default IngestionModeBanner;
