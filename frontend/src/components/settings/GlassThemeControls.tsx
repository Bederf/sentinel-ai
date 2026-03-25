import { useGlassTheme } from "../../hooks/useGlassTheme";
import { GLASS_PRESETS } from "../../lib/settings";

function GlassSwitch({ checked, onToggle }: { checked: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${checked ? "bg-blue-600" : "bg-gray-600"}`}
      aria-checked={checked}
      role="switch"
      type="button"
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${checked ? "translate-x-6" : "translate-x-1"}`}
      />
    </button>
  );
}

function GlassSectionLabel({
  detail,
  title,
}: {
  detail?: string;
  title: string;
}) {
  return (
    <div>
      <label className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
        {title}
      </label>
      {detail ? (
        <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {detail}
        </p>
      ) : null}
    </div>
  );
}

function GlassPresetSelector({ onSelect }: { onSelect: (preset: string) => void }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
        Quick Presets
      </label>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {Object.entries(GLASS_PRESETS).map(([name]) => (
          <button
            key={name}
            onClick={() => onSelect(name)}
            className="px-3 py-2 text-sm rounded border capitalize transition-colors hover:bg-opacity-80"
            style={{
              borderColor: "var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
            type="button"
          >
            {name}
          </button>
        ))}
      </div>
    </div>
  );
}

function GlassRangeControl({
  label,
  max,
  min,
  onChange,
  value,
  valueLabel,
  lowLabel,
  highLabel,
}: {
  highLabel: string;
  label: string;
  lowLabel: string;
  max: number;
  min: number;
  onChange: (nextValue: number) => void;
  value: number;
  valueLabel: string;
}) {
  return (
    <div>
      <div className="flex justify-between mb-2">
        <label className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
          {label}
        </label>
        <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {valueLabel}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number.parseInt(event.target.value, 10))}
        className="w-full h-3"
        style={{ cursor: "pointer" }}
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
      />
      <div className="flex justify-between text-xs mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
        <span>{lowLabel}</span>
        <span>{highLabel}</span>
      </div>
    </div>
  );
}

function GlassPreview() {
  return (
    <div className="glass-card p-4 space-y-3">
      <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
        Live Preview
      </p>
      <div className="glass-panel p-4 space-y-2">
        <div className="glass-card p-3">
          <p className="text-sm">Nested card example</p>
        </div>
        <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Adjust sliders above to see changes in real-time
        </p>
      </div>
    </div>
  );
}

function GlassResetButton({ onReset }: { onReset: () => void }) {
  return (
    <div className="pt-4 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
      <button
        onClick={onReset}
        className="px-4 py-2 text-sm rounded transition-colors hover:bg-opacity-80"
        style={{
          background: "var(--color-sentinel-bg-hover)",
          color: "var(--color-sentinel-text-primary)",
        }}
        type="button"
      >
        Reset to Default Theme
      </button>
    </div>
  );
}

function GlassThemeEnabledControls({
  applyPreset,
  borderStrength,
  blurIntensity,
  panelOpacity,
  updateSettings,
}: {
  applyPreset: (preset: string) => void;
  blurIntensity: number;
  borderStrength: number;
  panelOpacity: number;
  updateSettings: (settings: Partial<ReturnType<typeof useGlassTheme>["settings"]>) => void;
}) {
  return (
    <>
      <GlassPresetSelector onSelect={applyPreset} />
      <GlassRangeControl
        highLabel="Sharp"
        label="Blur Intensity"
        lowLabel="Subtle"
        max={30}
        min={0}
        onChange={(nextBlurIntensity) => updateSettings({ blurIntensity: nextBlurIntensity })}
        value={blurIntensity}
        valueLabel={`${blurIntensity}px`}
      />
      <GlassRangeControl
        highLabel="Solid"
        label="Panel Opacity"
        lowLabel="Transparent"
        max={95}
        min={20}
        onChange={(nextPanelOpacity) => updateSettings({ panelOpacity: nextPanelOpacity })}
        value={panelOpacity}
        valueLabel={`${panelOpacity}%`}
      />
      <GlassRangeControl
        highLabel="Prominent"
        label="Border Strength"
        lowLabel="Invisible"
        max={40}
        min={0}
        onChange={(nextBorderStrength) => updateSettings({ borderStrength: nextBorderStrength })}
        value={borderStrength}
        valueLabel={`${borderStrength}%`}
      />
      <GlassPreview />
    </>
  );
}

function GlassThemeCustomControls() {
  const { settings, updateSettings, resetToDefault, applyPreset } = useGlassTheme();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <GlassSectionLabel
          detail="Override default Apple Glass appearance"
          title="Enable Custom Glass Theme"
        />
        <GlassSwitch
          checked={settings.useCustomTheme}
          onToggle={() => updateSettings({ useCustomTheme: !settings.useCustomTheme })}
        />
      </div>

      {settings.useCustomTheme ? (
        <GlassThemeEnabledControls
          applyPreset={applyPreset}
          blurIntensity={settings.blurIntensity}
          borderStrength={settings.borderStrength}
          panelOpacity={settings.panelOpacity}
          updateSettings={updateSettings}
        />
      ) : null}

      <GlassResetButton onReset={resetToDefault} />
    </div>
  );
}

export function GlassThemeControls() {
  return <GlassThemeCustomControls />;
}
