import { useState, useCallback } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Sun,
  Zap,
} from 'lucide-react';

// ── Types ───────────────────────────────────────────────────────────────────

interface AuthField {
  key: string;
  label: string;
  type: 'email' | 'password' | 'text';
  required: boolean;
}

interface Platform {
  id: string;
  label: string;
  description: string;
  auth_fields: AuthField[];
}

interface DiscoveredDevice {
  device_id: string;
  device_name: string;
  device_type: string;
  capabilities: string[];
}

interface WizardState {
  step: 1 | 2 | 3 | 4 | 5 | 6;
  deploymentTier: 'full_simbiot' | 'cloud_only' | '';
  selectedPlatform: Platform | null;
  authCredentials: Record<string, string>;
  discoveredDevices: DiscoveredDevice[];
  eskomAreaCode: string;
  tariffType: 'prepaid' | 'time_of_use' | 'standard' | '';
  isLoading: boolean;
  error: string | null;
}

interface ResidentialOnboardingProps {
  siteId: string;
  onComplete: (result: { devicesDiscovered: number }) => void;
  onCancel: () => void;
}

// ── Constants ────────────────────────────────────────────────────────────────

const TARIFF_OPTIONS = [
  { value: 'prepaid' as const, label: 'Prepaid', description: 'Pre-purchased electricity tokens' },
  { value: 'time_of_use' as const, label: 'Time-of-Use (TOU)', description: 'Different rates at peak/off-peak times' },
  { value: 'standard' as const, label: 'Standard', description: 'Fixed tariff rate' },
];

const STEP_LABELS = [
  'Deployment',
  'Platform',
  'Credentials',
  'Discovery',
  'Location',
  'Confirm',
];

// ── Component ────────────────────────────────────────────────────────────────

export function ResidentialOnboarding({
  siteId,
  onComplete,
  onCancel,
}: ResidentialOnboardingProps) {
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [state, setState] = useState<WizardState>({
    step: 1,
    deploymentTier: '',
    selectedPlatform: null,
    authCredentials: {},
    discoveredDevices: [],
    eskomAreaCode: '',
    tariffType: '',
    isLoading: false,
    error: null,
  });

  const set = useCallback(
    (patch: Partial<WizardState>) => setState((s) => ({ ...s, ...patch })),
    [],
  );

  const loadPlatforms = useCallback(async () => {
    if (platforms.length > 0) return;
    try {
      const resp = await fetch('/api/residential/platforms');
      const data = await resp.json();
      setPlatforms(data.platforms ?? []);
    } catch {
      set({ error: 'Failed to load platform list' });
    }
  }, [platforms.length, set]);

  const runDiscovery = useCallback(async () => {
    if (!state.selectedPlatform) return;
    set({ isLoading: true, error: null });
    try {
      const resp = await fetch('/api/residential/onboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: siteId,
          platform: state.selectedPlatform.id,
          deployment_tier: state.deploymentTier,
          site_config: {
            site_id: siteId,
            ...state.authCredentials,
          },
          eskom_area_code: state.eskomAreaCode || null,
          tariff_type: state.tariffType || null,
        }),
      });

      if (resp.status === 401) {
        set({ isLoading: false, error: 'Authentication failed — check your credentials and try again.' });
        return;
      }
      if (resp.status === 504) {
        set({ isLoading: false, error: 'Discovery timed out (30s). Check your network or platform status.' });
        return;
      }
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
        set({ isLoading: false, error: err.detail ?? 'Onboarding failed' });
        return;
      }

      const result = await resp.json();
      set({ isLoading: false, step: 6 });
      onComplete({ devicesDiscovered: result.devices_discovered });
    } catch {
      set({ isLoading: false, error: 'Network error — could not reach the SENTINEL backend.' });
    }
  }, [state, siteId, set, onComplete]);

  const goNext = useCallback(() => {
    if (state.step === 2 && platforms.length === 0) {
      loadPlatforms();
    }
    set({ step: (state.step + 1) as WizardState['step'], error: null });
  }, [state.step, platforms.length, loadPlatforms, set]);

  const goBack = useCallback(() => {
    set({ step: (state.step - 1) as WizardState['step'], error: null });
  }, [state.step, set]);

  // ── Step renderers ─────────────────────────────────────────────────────────

  const renderStep1 = () => (
    <div className="space-y-4">
      <h3 className="font-semibold text-lg">Deployment Type</h3>
      <p className="text-sm text-muted-foreground">
        How is this residential/solar site connected to SENTINEL?
      </p>
      {(
        [
          {
            value: 'cloud_only' as const,
            label: 'Cloud-only',
            description: 'No edge device on-site. SENTINEL polls the platform cloud API from the VPS.',
          },
          {
            value: 'full_simbiot' as const,
            label: 'Full SIMBIOT (edge device)',
            description: 'SIMBIOT bridge device on-site with local connectivity.',
          },
        ] as const
      ).map((opt) => (
        <button
          key={opt.value}
          onClick={() => set({ deploymentTier: opt.value })}
          className={`w-full text-left p-4 rounded-lg border transition-colors ${
            state.deploymentTier === opt.value
              ? 'border-primary bg-primary/5'
              : 'border-border hover:border-primary/50'
          }`}
        >
          <div className="font-medium">{opt.label}</div>
          <div className="text-sm text-muted-foreground mt-1">{opt.description}</div>
        </button>
      ))}
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-4">
      <h3 className="font-semibold text-lg">Energy Platform</h3>
      <p className="text-sm text-muted-foreground">Select the monitoring platform for this site.</p>
      {platforms.length === 0 ? (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading platforms…
        </div>
      ) : (
        platforms
          .filter((p) => p.id !== 'other')
          .map((p) => (
            <button
              key={p.id}
              onClick={() => set({ selectedPlatform: p, authCredentials: {} })}
              className={`w-full text-left p-4 rounded-lg border transition-colors ${
                state.selectedPlatform?.id === p.id
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50'
              }`}
            >
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-yellow-500" />
                <span className="font-medium">{p.label}</span>
              </div>
              <div className="text-sm text-muted-foreground mt-1">{p.description}</div>
            </button>
          ))
      )}
    </div>
  );

  const renderStep3 = () => {
    const fields = state.selectedPlatform?.auth_fields ?? [];
    return (
      <div className="space-y-4">
        <h3 className="font-semibold text-lg">{state.selectedPlatform?.label} Credentials</h3>
        <p className="text-sm text-muted-foreground">
          Credentials are stored securely and never logged.
        </p>
        {fields.map((f) => (
          <div key={f.key} className="space-y-1">
            <label className="text-sm font-medium">
              {f.label}
              {f.required && <span className="text-destructive ml-1">*</span>}
            </label>
            <input
              type={f.type}
              className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm"
              value={state.authCredentials[f.key] ?? ''}
              onChange={(e) =>
                set({ authCredentials: { ...state.authCredentials, [f.key]: e.target.value } })
              }
              autoComplete={f.type === 'password' ? 'new-password' : 'off'}
            />
          </div>
        ))}
      </div>
    );
  };

  const renderStep4 = () => (
    <div className="space-y-4">
      <h3 className="font-semibold text-lg">Location & Tariff</h3>
      <div className="space-y-1">
        <label className="text-sm font-medium">Eskom Area Code</label>
        <input
          type="text"
          placeholder="e.g. KZN-2-16"
          className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm"
          value={state.eskomAreaCode}
          onChange={(e) => set({ eskomAreaCode: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">Used for loadshedding schedule overlay.</p>
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium">Tariff Type</label>
        {TARIFF_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => set({ tariffType: opt.value })}
            className={`w-full text-left p-3 rounded-lg border transition-colors ${
              state.tariffType === opt.value
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/50'
            }`}
          >
            <div className="font-medium text-sm">{opt.label}</div>
            <div className="text-xs text-muted-foreground">{opt.description}</div>
          </button>
        ))}
      </div>
    </div>
  );

  const renderStep5 = () => (
    <div className="space-y-4">
      <h3 className="font-semibold text-lg">Confirm Onboarding</h3>
      <div className="rounded-lg border border-border p-4 space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Site</span>
          <span className="font-mono">{siteId}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Platform</span>
          <span>{state.selectedPlatform?.label}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Deployment</span>
          <span>{state.deploymentTier === 'cloud_only' ? 'Cloud-only' : 'Full SIMBIOT'}</span>
        </div>
        {state.eskomAreaCode && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Eskom area</span>
            <span>{state.eskomAreaCode}</span>
          </div>
        )}
        {state.tariffType && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Tariff</span>
            <span className="capitalize">{state.tariffType.replace('_', ' ')}</span>
          </div>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        SENTINEL will authenticate with {state.selectedPlatform?.label}, discover devices, and
        start polling every 5 minutes. This may take up to 30 seconds.
      </p>
    </div>
  );

  const renderStep6 = () => (
    <div className="flex flex-col items-center gap-4 py-6">
      <CheckCircle2 className="h-12 w-12 text-green-500" />
      <h3 className="font-semibold text-lg">Onboarding Complete</h3>
      <p className="text-sm text-muted-foreground text-center">
        Site <span className="font-mono">{siteId}</span> has been onboarded and polling has begun.
      </p>
    </div>
  );

  const stepContent: Record<number, () => JSX.Element> = {
    1: renderStep1,
    2: renderStep2,
    3: renderStep3,
    4: renderStep4,
    5: renderStep5,
    6: renderStep6,
  };

  const canProceed = (): boolean => {
    switch (state.step) {
      case 1: return state.deploymentTier !== '';
      case 2: return state.selectedPlatform !== null;
      case 3: {
        const fields = state.selectedPlatform?.auth_fields ?? [];
        return fields.filter((f) => f.required).every((f) => !!state.authCredentials[f.key]);
      }
      case 4: return state.tariffType !== '';
      case 5: return true;
      default: return false;
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-lg mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Sun className="h-6 w-6 text-yellow-500" />
        <div>
          <h2 className="font-semibold text-xl">Residential Energy Onboarding</h2>
          <p className="text-sm text-muted-foreground">Step {state.step} of 6 — {STEP_LABELS[state.step - 1]}</p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-primary transition-all"
          style={{ width: `${((state.step - 1) / 5) * 100}%` }}
        />
      </div>

      {/* Step content */}
      <div className="min-h-64">{(stepContent[state.step] ?? (() => null))()}</div>

      {/* Error */}
      {state.error && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          {state.error}
        </div>
      )}

      {/* Navigation */}
      {state.step < 6 && (
        <div className="flex justify-between">
          <button
            onClick={state.step === 1 ? onCancel : goBack}
            className="flex items-center gap-1 px-4 py-2 rounded-md border border-border text-sm hover:bg-muted transition-colors"
          >
            <ChevronLeft className="h-4 w-4" />
            {state.step === 1 ? 'Cancel' : 'Back'}
          </button>

          {state.step < 5 ? (
            <button
              onClick={goNext}
              disabled={!canProceed()}
              className="flex items-center gap-1 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={runDiscovery}
              disabled={state.isLoading}
              className="flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {state.isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Connecting…
                </>
              ) : (
                <>
                  <Zap className="h-4 w-4" />
                  Onboard Site
                </>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
