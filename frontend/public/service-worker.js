/**
 * SENTINEL Service Worker - PWA foundation.
 *
 * Strategy:
 * - Precache the app shell and install metadata.
 * - Network-first for SPA navigations, with cached shell fallback.
 * - Stale-while-revalidate for same-origin static assets.
 * - Network-first with cached fallback for decision payloads.
 */

const APP_VERSION = "v6";
const APP_SHELL_CACHE = `sentinel-shell-${APP_VERSION}`;
const STATIC_CACHE = `sentinel-static-${APP_VERSION}`;
const PAYLOAD_CACHE = `sentinel-payload-${APP_VERSION}`;

const APP_SHELL_URLS = [
  "/",
  "/index.html",
  "/manifest.json",
  "/images/sentinel-logo.png",
  "/icons/icon-192.svg",
  "/icons/icon-512.svg",
];

const PAYLOAD_PATTERN = /\/api\/decisions\/current\//;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(APP_SHELL_CACHE).then((cache) => cache.addAll(APP_SHELL_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      self.clients.claim(),
      caches.keys().then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("sentinel-") && ![APP_SHELL_CACHE, STATIC_CACHE, PAYLOAD_CACHE].includes(key))
            .map((key) => caches.delete(key))
        )
      ),
    ])
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== "GET") {
    return;
  }

  if (PAYLOAD_PATTERN.test(request.url)) {
    event.respondWith(networkFirstWithCache(request));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(networkFirstAppShell(request));
    return;
  }

  if (url.origin === self.location.origin && isStaticAsset(url)) {
    event.respondWith(networkFirstStatic(request));
  }
});

function isStaticAsset(url) {
  return (
    url.pathname.startsWith("/assets/") ||
    url.pathname.startsWith("/icons/") ||
    url.pathname.startsWith("/images/") ||
    url.pathname.startsWith("/audio/") ||
    url.pathname === "/manifest.json" ||
    url.pathname === "/vite.svg"
  );
}

async function networkFirstAppShell(request) {
  const cache = await caches.open(APP_SHELL_CACHE);

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put("/index.html", networkResponse.clone());
    }
    return networkResponse;
  } catch (_networkError) {
    return (
      (await cache.match("/index.html")) ||
      (await cache.match("/")) ||
      new Response("SENTINEL is offline and the app shell is not cached yet.", {
        status: 503,
        headers: { "Content-Type": "text/plain" },
      })
    );
  }
}

async function networkFirstStatic(request) {
  const cache = await caches.open(STATIC_CACHE);

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok && isExpectedStaticResponse(request, networkResponse)) {
      cache.put(request, networkResponse.clone());
      return networkResponse;
    }

    const cachedResponse = await cache.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    return new Response("Static asset not found.", {
      status: 404,
      headers: { "Content-Type": "text/plain", "Cache-Control": "no-store" },
    });
  } catch (_networkError) {
    return (
      (await cache.match(request)) ||
      new Response("Static asset unavailable.", {
        status: 503,
        headers: { "Content-Type": "text/plain", "Cache-Control": "no-store" },
      })
    );
  }
}

function isExpectedStaticResponse(request, response) {
  const destination = request.destination;
  const contentType = response.headers.get("Content-Type") || "";

  if (destination === "script") {
    return contentType.includes("javascript");
  }
  if (destination === "style") {
    return contentType.includes("css");
  }
  if (destination === "image") {
    return contentType.startsWith("image/");
  }
  if (destination === "audio") {
    return contentType.startsWith("audio/");
  }
  if (request.url.endsWith("/manifest.json")) {
    return contentType.includes("json") || contentType.includes("manifest");
  }

  return !contentType.includes("text/html");
}

/**
 * Network-first strategy for decision payloads.
 *
 * 1. Try the network - fastest path, always fresh
 * 2. On success: clone response into cache, return to caller
 * 3. On network failure: return cached payload if available
 * 4. If no cache: return a minimal offline response
 */
async function networkFirstWithCache(request) {
  const cache = await caches.open(PAYLOAD_CACHE);

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (_networkError) {
    const cachedResponse = await cache.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    return new Response(
      JSON.stringify({
        _offline: true,
        urgency_score: 0,
        renderer_hint: "quiet",
        alert_text: "SENTINEL offline - showing last known state unavailable.",
        building_id: null,
        primary_asset_id: null,
        affected_zone_ids: [],
        reasoning_summary: "Backend unreachable. Last cached payload not found.",
        active_posture: "unknown",
        posture_weights: { comfort: 0.7, cost: 0.15, asset: 0.15 },
        recommended_action: "Check network connectivity.",
        action_validation_state: "unverified",
        time_to_discomfort: null,
        time_confidence: "unavailable",
        estimated_impact: "Unknown - system offline.",
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
