import { useState, useEffect, useCallback } from "react";
import { Coins, RefreshCw, TrendingUp } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface ModelUsage {
  calls: number;
  tokens: number;
  cost_usd: number;
  cost_zar: number;
}

interface DailyCost {
  date: string;
  cost_usd: number;
  cost_zar: number;
  tokens: number;
}

interface TodayModel {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  cost_zar: number;
}

interface UsageSummary {
  period_days: number;
  usd_zar_rate: number;
  total_cost_usd: number;
  total_cost_zar: number;
  total_tokens: number;
  by_provider: Record<string, ModelUsage>;
  by_model: Record<string, ModelUsage>;
  by_source?: Record<string, ModelUsage>;
  daily: DailyCost[];
  budget?: {
    monthly_budget_zar: number;
    spent_zar: number;
    remaining_zar: number;
    hard_cap_enforced: boolean;
    over_budget: boolean;
  };
}

interface TodayUsage {
  date: string;
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  total_cost_zar: number;
  models: Record<string, TodayModel>;
  by_source?: Record<string, ModelUsage>;
}

interface AiCostTrackerProps {
  siteId?: string;
  onError?: (error: string) => void;
}

const PERIOD_OPTIONS = [
  { value: 7, label: "7 days" },
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
];

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: "var(--color-sentinel-blue)",
  openai: "var(--color-sentinel-green)",
  ollama: "rgb(168, 85, 247)",
  sentry: "var(--color-sentinel-amber)",
  elevenlabs: "var(--color-sentinel-red)",
  zhipuai: "rgb(56, 189, 248)",
  whatsapp_meta: "rgb(37, 211, 102)",
  whatsapp_twilio: "rgb(37, 211, 102)",
  bulksms: "rgb(251, 146, 60)",
  telegram: "rgb(0, 136, 204)",
  eskomsepush: "rgb(239, 68, 68)",
};

export function AiCostTracker({ siteId, onError }: AiCostTrackerProps) {
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [today, setToday] = useState<TodayUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(30);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [sumRes, todayRes] = await Promise.all([
        authorizedFetch(`/api/ai-usage/summary?days=${period}${siteId ? `&site_id=${encodeURIComponent(siteId)}` : ""}`),
        authorizedFetch(`/api/ai-usage/today${siteId ? `?site_id=${encodeURIComponent(siteId)}` : ""}`),
      ]);

      if (sumRes.ok) setSummary(await sumRes.json());
      if (todayRes.ok) setToday(await todayRes.json());
    } catch {
      onError?.("Failed to load AI usage data");
    } finally {
      setLoading(false);
    }
  }, [period, onError, siteId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const fmt = (n: number, decimals = 2) =>
    n.toLocaleString("en-ZA", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

  const fmtTokens = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  };

  // Find max daily cost for chart scaling
  const maxDailyCost = summary ? Math.max(...summary.daily.map((d) => d.cost_zar), 0.01) : 1;
  const topCostlyRoutes = summary?.by_source
    ? Object.entries(summary.by_source)
      .sort(([, a], [, b]) => b.cost_zar - a.cost_zar)
      .slice(0, 10)
    : [];

  return (
    <div className="glass-panel overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}>
              <Coins className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>API & Service Costs</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Spend across AI, messaging, and external services
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded overflow-hidden" style={{ border: "1px solid var(--glass-border)" }}>
              {PERIOD_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setPeriod(opt.value)}
                  className="px-2 py-1 text-[10px] font-medium transition-colors"
                  style={{
                    background: period === opt.value ? "rgba(59, 130, 246, 0.15)" : "transparent",
                    color: period === opt.value ? "var(--color-sentinel-blue)" : "var(--color-sentinel-text-secondary)",
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <button type="button" onClick={() => void fetchData()} className="p-1.5 rounded" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      </div>

      <div className="p-4 space-y-5">
        {loading && !summary ? (
          <p className="text-sm text-center py-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading usage data...</p>
        ) : (
          <>
            {/* Today's snapshot */}
            {today && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard label="Today's Spend" value={`R ${fmt(today.total_cost_zar)}`} sub={`$${fmt(today.total_cost_usd, 4)}`} color="var(--color-sentinel-amber)" />
                <StatCard label="Today's Calls" value={String(today.total_calls)} sub="API requests" color="var(--color-sentinel-blue)" />
                <StatCard label="Today's Tokens" value={fmtTokens(today.total_tokens)} sub="input + output" color="var(--color-sentinel-green)" />
                <StatCard
                  label={`${period}-Day Total`}
                  value={summary ? `R ${fmt(summary.total_cost_zar)}` : "—"}
                  sub={summary ? `$${fmt(summary.total_cost_usd, 4)}` : ""}
                  color="rgb(168, 85, 247)"
                />
              </div>
            )}

            {summary?.budget && summary.budget.monthly_budget_zar > 0 && (
              <div
                className="p-3 rounded-lg"
                style={{
                  background: summary.budget.over_budget ? "rgba(239, 68, 68, 0.12)" : "rgba(59, 130, 246, 0.12)",
                  border: `1px solid ${summary.budget.over_budget ? "rgba(239,68,68,0.5)" : "rgba(59,130,246,0.5)"}`,
                }}
              >
                <div className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Budget: R {fmt(summary.budget.spent_zar)} / R {fmt(summary.budget.monthly_budget_zar)}
                  {summary.budget.hard_cap_enforced ? " (hard cap enabled)" : ""}
                </div>
                <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Remaining: R {fmt(summary.budget.remaining_zar)}
                </div>
              </div>
            )}

            {/* Daily cost chart (simple bar chart) */}
            {summary && summary.daily.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Daily Spend (ZAR)
                </h3>
                <div className="flex items-end gap-[2px] h-20">
                  {summary.daily.map((d) => {
                    const pct = Math.max((d.cost_zar / maxDailyCost) * 100, 2);
                    return (
                      <div
                        key={d.date}
                        className="flex-1 rounded-t transition-all group relative"
                        style={{
                          height: `${pct}%`,
                          background: "var(--color-sentinel-blue)",
                          minWidth: "3px",
                          opacity: 0.7,
                        }}
                        title={`${d.date}: R${fmt(d.cost_zar)} (${fmtTokens(d.tokens)} tokens)`}
                      />
                    );
                  })}
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-[9px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {summary.daily[0]?.date}
                  </span>
                  <span className="text-[9px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {summary.daily[summary.daily.length - 1]?.date}
                  </span>
                </div>
              </div>
            )}

            {/* By provider */}
            {summary && Object.keys(summary.by_provider).length > 0 && (
              <div>
                <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  By Provider
                </h3>
                <div className="space-y-2">
                  {Object.entries(summary.by_provider).map(([provider, data]) => {
                    const color = PROVIDER_COLORS[provider] || "var(--color-sentinel-text-secondary)";
                    const pct = summary.total_cost_usd > 0 ? (data.cost_usd / summary.total_cost_usd) * 100 : 0;
                    return (
                      <div key={provider} className="p-2.5 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-2 rounded-full" style={{ background: color }} />
                            <span className="text-xs font-medium capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>
                              {provider}
                            </span>
                            <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                              {data.calls} calls
                            </span>
                          </div>
                          <div className="text-right">
                            <span className="text-xs font-semibold" style={{ color }}>R {fmt(data.cost_zar)}</span>
                            <span className="text-[10px] ml-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                              ({fmt(pct, 0)}%)
                            </span>
                          </div>
                        </div>
                        <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--color-sentinel-bg-hover)" }}>
                          <div className="h-full rounded-full" style={{ width: `${Math.max(pct, 1)}%`, background: color }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {summary && summary.by_source && Object.keys(summary.by_source).length > 0 && (
              <div>
                <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  By Route / Source
                </h3>
                <div className="space-y-1">
                  {Object.entries(summary.by_source).map(([source, data]) => (
                    <div key={source} className="flex items-center justify-between py-1.5 px-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                      <div>
                        <span className="text-xs font-mono" style={{ color: "var(--color-sentinel-text-primary)" }}>{source}</span>
                        <span className="text-[10px] ml-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          {data.calls} calls · {fmtTokens(data.tokens)} tokens
                        </span>
                      </div>
                      <span className="text-xs font-semibold" style={{ color: "var(--color-sentinel-amber)" }}>
                        R {fmt(data.cost_zar)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {topCostlyRoutes.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Top 10 Costly Routes (This Period)
                </h3>
                <div className="space-y-1">
                  {topCostlyRoutes.map(([source, data], index) => (
                    <div
                      key={source}
                      className="flex items-center justify-between py-1.5 px-2 rounded"
                      style={{ background: "var(--color-sentinel-bg-secondary)" }}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className="text-[10px] font-semibold w-5 text-center"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          #{index + 1}
                        </span>
                        <span className="text-xs font-mono" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {source}
                        </span>
                      </div>
                      <span className="text-xs font-semibold" style={{ color: "var(--color-sentinel-amber)" }}>
                        R {fmt(data.cost_zar)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* By model */}
            {summary && Object.keys(summary.by_model).length > 0 && (
              <div>
                <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  By Model
                </h3>
                <div className="space-y-1">
                  {Object.entries(summary.by_model).map(([model, data]) => (
                    <div key={model} className="flex items-center justify-between py-1.5 px-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                      <div>
                        <span className="text-xs font-mono" style={{ color: "var(--color-sentinel-text-primary)" }}>{model}</span>
                        <span className="text-[10px] ml-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          {data.calls} calls · {fmtTokens(data.tokens)} tokens
                        </span>
                      </div>
                      <span className="text-xs font-semibold" style={{ color: "var(--color-sentinel-amber)" }}>
                        R {fmt(data.cost_zar)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Exchange rate */}
            {summary && (
              <div className="flex items-center justify-between pt-2" style={{ borderTop: "1px solid var(--glass-border)" }}>
                <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Exchange rate: 1 USD = R {fmt(summary.usd_zar_rate)}
                </span>
                <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  <TrendingUp className="h-3 w-3 inline mr-1" />
                  Pricing updated 2026-03
                </span>
              </div>
            )}

            {/* No data state */}
            {summary && summary.daily.length === 0 && (
              <div className="text-center py-6">
                <Coins className="h-8 w-8 mx-auto mb-2" style={{ color: "var(--color-sentinel-text-secondary)", opacity: 0.3 }} />
                <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>No AI usage recorded yet</p>
                <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Costs will appear here after the first chat or AI operation
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
      <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>{label}</p>
      <p className="text-lg font-semibold mt-0.5" style={{ color }}>{value}</p>
      <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>{sub}</p>
    </div>
  );
}
