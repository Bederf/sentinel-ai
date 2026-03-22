/**
 * SENTINEL Service Worker — PWA Foundation
 *
 * Strategy: network-first for decision payloads.
 * If the backend is unreachable (Jetson restart, LAN drop), the kiosk
 * serves the last cached payload so the operator sees the last known state
 * rather than a blank screen.
 *
 * Scope: only intercepts /api/decisions/current/* — everything else passes through.
 *
 * Future phases:
 *   Push notifications  — subscribe to push events here, show urgency alerts
 *   3D renderer assets  — cache GLTF/draco files in a separate STATIC_CACHE
 */

const PAYLOAD_CACHE = "sentinel-payload-v1";

// Only cache decision payload responses — not the whole app shell
const PAYLOAD_PATTERN = /\/api\/decisions\/current\//;

self.addEventListener("install", (event) => {
  // Activate immediately — don't wait for old tabs to close
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Take control of all clients immediately
  event.waitUntil(self.clients.claim());

  // Prune old payload caches from previous versions
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith("sentinel-payload-") && k !== PAYLOAD_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only intercept GET requests to the decision payload endpoint
  if (request.method !== "GET" || !PAYLOAD_PATTERN.test(request.url)) {
    return; // pass through — do not intercept
  }

  event.respondWith(networkFirstWithCache(request));
});

/**
 * Network-first strategy for decision payloads.
 *
 * 1. Try the network — fastest path, always fresh
 * 2. On success: clone response into cache, return to caller
 * 3. On network failure: return cached payload if available
 * 4. If no cache: propagate the error (caller handles gracefully)
 */
async function networkFirstWithCache(request) {
  const cache = await caches.open(PAYLOAD_CACHE);

  try {
    const networkResponse = await fetch(request);

    // Only cache valid 2xx responses — don't cache 422 (no active fault)
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (_networkError) {
    // Network unavailable — serve last known payload
    const cachedResponse = await cache.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    // No cache and no network — return a minimal offline response
    // so the kiosk renders a degraded state rather than throwing
    return new Response(
      JSON.stringify({
        _offline: true,
        urgency_score: 0,
        renderer_hint: "quiet",
        alert_text: "SENTINEL offline — showing last known state unavailable.",
        building_id: null,
        primary_asset_id: null,
        affected_zone_ids: [],
        reasoning_summary: "Backend unreachable. Last cached payload not found.",
        active_posture: "unknown",
        posture_weights: { comfort: 0.7, cost: 0.15, asset: 0.15 },
        recommended_action: "Check network connectivity to Jetson.",
        action_validation_state: "unverified",
        time_to_discomfort: null,
        time_confidence: "unavailable",
        estimated_impact: "Unknown — system offline.",
        building_metadata: {
          has_spatial_data: false,
          floor_stack: [],
          floor_stack_order: [],
          floor_labels: {},
          floors_count: 0,
          deployment_mode: "ghost",
        },
        active_incident_map: {},
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json", "X-Served-By": "sentinel-sw-offline" },
      }
    );
  }
}
