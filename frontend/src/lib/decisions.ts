const SITE_DECISION_FALLBACK_ASSETS: Record<string, string> = {
  "site-002": "S002-CHILLER-B1-001",
};

export function buildCurrentDecisionUrl(siteId: string): string {
  const params = new URLSearchParams();
  const fallbackAssetId = SITE_DECISION_FALLBACK_ASSETS[siteId];

  if (fallbackAssetId) {
    params.set("asset_id", fallbackAssetId);
  }

  const query = params.size > 0 ? `?${params.toString()}` : "";
  return `/api/decisions/current/${encodeURIComponent(siteId)}${query}`;
}
