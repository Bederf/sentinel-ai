/**
 * AimTheLaw Optimized Cloudflare Worker (Edge-first caching)
 * - Edge Cache first (free)
 * - KV index avoids KV.get "not found" spam
 * - Negative caching for 404/410
 * Safeguards:
 * - Skips caching for auth'd requests
 * - Proper OPTIONS/HEAD handling
 * - Tight headers + Server-Timing
 */

import { handleDemoRequest } from './demo-handler.js';

const INDEX_KEY = "safe-cache:index";  // JSON array of cached pathnames
const CACHE_PREFIX = "safe-cache:";    // KV value prefix
const NEG_PREFIX = "neg:";             // negative-cache marker

const INDEX_TTL_SECS = 300;            // 5 min edge cache for the index
const NEG_TTL_SECS = 600;              // 10 min remember 404/410
const MAX_INDEX_SIZE = 5000;           // cap index

const MINIMAL_SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-XSS-Protection": "1; mode=block",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
};

// SECURITY: Allowed CORS origins - must match backend configuration
const ALLOWED_ORIGINS = [
  "https://sentinel-ai.co.za",
  "https://app.aimthelaw.co.za",
  "https://api.aimthelaw.co.za",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

// Check if origin is allowed for CORS
function isAllowedOrigin(origin) {
  if (!origin) return false;
  return ALLOWED_ORIGINS.includes(origin);
}

// Whitelist cacheable paths and TTLs (seconds)
const CACHE_DURATIONS = {
  "/api/health": 30,
  "/api/config": 300,
  "/api/static": 3600,
  "/api/clients": 60,
  "/api/lawyers": 60,
  "/health": 30,
  "/api/status": 30,
  "/api/public/info": 300,
  "/api/public/contact": 300,
};

// ---- KV helpers ----
async function getIndex(env) {
  const raw = await env.MY_APP_STORAGE.get(INDEX_KEY, { cacheTtl: INDEX_TTL_SECS });
  if (!raw) return new Set();
  try { return new Set(JSON.parse(raw)); } catch { return new Set(); }
}

async function addToIndex(env, path) {
  const set = await getIndex(env);
  if (set.has(path)) return;
  set.add(path);

  if (set.size > MAX_INDEX_SIZE) {
    const arr = Array.from(set);
    const trimmed = arr.slice(-Math.floor(MAX_INDEX_SIZE * 0.8)); // keep newest ~80%
    await env.MY_APP_STORAGE.put(INDEX_KEY, JSON.stringify(trimmed));
  } else {
    await env.MY_APP_STORAGE.put(INDEX_KEY, JSON.stringify([...set]));
  }
}

async function removeFromIndex(env, path) {
  const set = await getIndex(env);
  if (!set.has(path)) return;
  set.delete(path);
  await env.MY_APP_STORAGE.put(INDEX_KEY, JSON.stringify([...set]));
}

function kvKey(pathname) { return `${CACHE_PREFIX}${pathname}`; }
function negKey(pathname) { return `${NEG_PREFIX}${pathname}`; }

// Finalize response with consistent headers
function finalize(response, cacheStatus, origin = null) {
  const headers = new Headers(response.headers);
  headers.set("X-Cache", cacheStatus);
  headers.set("X-Worker", "aimthelaw-opt-prod-v1");
  headers.set("Server-Timing", `phase;desc="${cacheStatus}"`);

  // Add CORS headers if origin is allowed
  if (origin && isAllowedOrigin(origin)) {
    headers.set("Access-Control-Allow-Origin", origin);
    headers.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH");
    headers.set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-CSRF-Token, X-Requested-With");
    headers.set("Access-Control-Allow-Credentials", "true");
  }

  // Add security headers
  Object.entries(MINIMAL_SECURITY_HEADERS).forEach(([key, value]) => {
    if (!headers.has(key)) headers.set(key, value);
  });

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

// ---- Cache helpers ----
function shouldCache(pathname) {
  return Object.keys(CACHE_DURATIONS).some((p) => pathname.startsWith(p));
}

function getCacheDuration(pathname) {
  for (const [p, ttl] of Object.entries(CACHE_DURATIONS)) {
    if (pathname.startsWith(p)) return ttl;
  }
  return 60; // default
}

function buildVaryHeader(request, existingVary) {
  const vary = ["Accept-Encoding", "Accept", "Origin"];
  if (request.headers.has("Authorization")) vary.push("Authorization");
  if (request.headers.has("Cookie")) vary.push("Cookie");
  const existing = (existingVary || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const combined = Array.from(new Set([...existing, ...vary])).filter(Boolean);
  return combined.join(", ");
}

// ---- Origin fetch (safe) ----
async function handleOrigin(request) {
  const inUrl = new URL(request.url);
  const outUrl = new URL(inUrl);

  // Route based on hostname: SENTINEL BMS backend vs AimTheLaw backend
  if (inUrl.hostname === "api.sentinel-ai.co.za") {
    // SENTINEL BMS — route directly to local VPS backend (port 9095)
    outUrl.hostname = "144.91.122.235";
    outUrl.port = "9095";
  } else {
    // AimTheLaw — route to appropriate backend
    outUrl.hostname = inUrl.pathname.startsWith("/api")
      ? "api.aimthelaw.co.za"
      : "app.aimthelaw.co.za";
  }

  const headers = new Headers(request.headers);
  // Strip hop-by-hop / forbidden headers (Host handled automatically by fetch)
  ["connection", "keep-alive", "transfer-encoding", "upgrade",
   "proxy-authenticate", "proxy-authorization", "te", "trailers"].forEach((h) =>
    headers.delete(h)
  );

  const outReq = new Request(outUrl.toString(), {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    redirect: "follow",
  });

  return fetch(outReq);
}

// ---- Email Handler ----
// Receives emails via Cloudflare Email Routing and forwards to N8N webhook
async function handleEmail(message, env, ctx) {
  const from = message.from;
  const to = message.to;
  const subject = message.headers.get("subject") || "(No Subject)";
  const messageId = message.headers.get("message-id") || "";
  const date = message.headers.get("date") || new Date().toISOString();

  // Read the raw email
  const rawEmail = await new Response(message.raw).text();

  // Parse sender email and name
  let senderEmail = from;
  let senderName = from;
  const emailMatch = from.match(/<([^>]+)>/);
  if (emailMatch) {
    senderEmail = emailMatch[1];
    senderName = from.split('<')[0].trim() || senderEmail;
  }
  const senderEmailNormalized = senderEmail.toLowerCase().trim();

  // Ignore bounce/notification senders to avoid noisy client lookups
  if (
    senderEmailNormalized.includes("notify.cloudflare.com") ||
    senderEmailNormalized.startsWith("msprvs1=")
  ) {
    console.log(`Skipping bounce sender: ${senderEmailNormalized}`);
    return;
  }

  // Extract plain text body
  let body = "";
  const boundaryMatch = rawEmail.match(/boundary="?([^"\r\n]+)"?/i);
  if (boundaryMatch) {
    const boundary = boundaryMatch[1];
    const parts = rawEmail.split('--' + boundary);
    for (const part of parts) {
      if (part.includes('Content-Type: text/plain')) {
        const bodyMatch = part.split(/\r?\n\r?\n/);
        if (bodyMatch.length > 1) {
          body = bodyMatch.slice(1).join('\n\n').trim().replace(/--$/, '').trim();
          break;
        }
      }
    }
  } else {
    const bodyMatch = rawEmail.split(/\r?\n\r?\n/);
    if (bodyMatch.length > 1) {
      body = bodyMatch.slice(1).join('\n\n').trim();
    }
  }

  if (!body) body = "(Email body could not be extracted)";

  // Prepare webhook payload (matches N8N Email Intake Router format)
  const payload = {
    from: senderEmail.toLowerCase().trim(),
    from_name: senderName,
    to: to,
    subject: subject,
    body: body,
    text: body,  // alias for body
    message_id: messageId,
    date: date,
    // Also include original format for compatibility
    sender_email: senderEmailNormalized,
    sender_name: senderName,
    recipient_email: to,
    received_at: date,
    source: "cloudflare_email_worker"
  };

  // Send directly to backend API (bypassing N8N for simplicity)
  const backendUrl = env.BACKEND_API_URL || "https://api.aimthelaw.co.za/api/email/inbound-autorespond";

  // Backend expects: sender_email, sender_name, subject, body
  const backendPayload = {
    sender_email: payload.sender_email,
    sender_name: payload.sender_name,
    subject: payload.subject,
    body: payload.body
  };

  try {
    const response = await fetch(backendUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(backendPayload),
    });

    const responseText = await response.text();

    if (!response.ok) {
      console.error(`Backend API failed: ${response.status} - ${responseText}`);
      return;
    } else {
      console.log(`Email from ${senderEmail} processed by backend API`);
    }
  } catch (error) {
    console.error(`Backend API error: ${error.message}`);
    return;
  }
}

// ---- Worker ----
export default {
  // Email handler for Cloudflare Email Routing
  async email(message, env, ctx) {
    return handleEmail(message, env, ctx);
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const method = request.method;

    // WebSocket connections need special handling - pass through directly
    // CRITICAL: WebSocket upgrades cannot be modified or wrapped
    const upgradeHeader = request.headers.get("Upgrade");
    if (upgradeHeader && upgradeHeader.toLowerCase() === "websocket") {
      return fetch(request);
    }

    // Demo request handler for Sentinel
    if (url.pathname === "/api/demo-request" || url.pathname === "/" && method === "POST") {
      return handleDemoRequest(request, env);
    }

    // CORS preflight - SECURITY: Only allow configured origins
    if (method === "OPTIONS") {
      const origin = request.headers.get("Origin");

      // SECURITY: Reject requests from unknown origins
      if (!isAllowedOrigin(origin)) {
        console.log(`CORS rejected: Origin "${origin}" not in allowed list`);
        return new Response("Forbidden", {
          status: 403,
          headers: MINIMAL_SECURITY_HEADERS
        });
      }

      const resp = new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": origin,  // Echo the allowed origin, not "*"
          "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
          "Access-Control-Allow-Headers": "Content-Type, Authorization, X-CSRF-Token, X-Requested-With",
          "Access-Control-Allow-Credentials": "true",
          "Access-Control-Max-Age": "86400",
        },
      });
      return finalize(resp, "OPTIONS");
    }

    // HEAD or non-GET → don't cache
    if (method === "HEAD" || method !== "GET") {
      return finalize(await handleOrigin(request), "BYPASS-METHOD");
    }

    // Skip caching for authenticated requests
    if (request.headers.has("Authorization") || request.headers.has("Cookie")) {
      return finalize(await handleOrigin(request), "BYPASS-AUTH");
    }

    // Only cache whitelisted paths
    if (!shouldCache(url.pathname)) {
      return finalize(await handleOrigin(request), "BYPASS-PATH");
    }

    // 1) Free Edge cache first
    const cache = caches.default;
    const cacheReq = new Request(url.toString(), request);
    const edgeHit = await cache.match(cacheReq);
    if (edgeHit) {
      return finalize(edgeHit, "HIT-EDGE");
    }

    // 2) Negative cache gate (404/410)
    const neg = await env.MY_APP_STORAGE.get(negKey(url.pathname), { cacheTtl: INDEX_TTL_SECS });
    if (neg) {
      const resp = new Response("Not found (cached)", {
        status: 404,
        headers: {
          ...MINIMAL_SECURITY_HEADERS,
          "Content-Type": "text/plain; charset=utf-8",
        },
      });
      return finalize(resp, "NEG-HIT");
    }

    // 3) KV index gate
    const index = await getIndex(env);
    if (index.has(url.pathname)) {
      const cachedBody = await env.MY_APP_STORAGE.get(kvKey(url.pathname));
      if (cachedBody !== null) {
        const ttl = getCacheDuration(url.pathname);
        const headers = new Headers(MINIMAL_SECURITY_HEADERS);
        headers.set("Content-Type", "application/json; charset=utf-8");
        headers.set("Cache-Control", `public, max-age=${ttl}`);
        headers.set("Vary", buildVaryHeader(request, null));

        const resp = new Response(cachedBody, { headers });
        ctx.waitUntil(cache.put(cacheReq, resp.clone())); // hydrate edge
        return finalize(resp, "HIT-KV");
      } else {
        // stale index entry → clean it up
        ctx.waitUntil(removeFromIndex(env, url.pathname));
      }
    }

    // 4) Origin fetch
    let originRes;
    try {
      originRes = await handleOrigin(request);
    } catch (err) {
      console.error("Origin fetch error:", err);
      return new Response("Gateway Error", {
        status: 502,
        headers: {
          ...MINIMAL_SECURITY_HEADERS,
          "Content-Type": "text/plain; charset=utf-8",
          "Server-Timing": 'phase;desc="ORIGIN-ERROR"',
        },
      });
    }

    // Clone for body + headers reuse
    const [resForClient, resForCache] = [originRes.clone(), originRes.clone()];
    const ttl = getCacheDuration(url.pathname);

    // 5) Cache good responses; negative-cache misses
    if (originRes.status >= 200 && originRes.status < 300) {
      const body = await resForCache.text();

      // KV write-through + index update
      ctx.waitUntil(env.MY_APP_STORAGE.put(kvKey(url.pathname), body, { expirationTtl: ttl }));
      ctx.waitUntil(addToIndex(env, url.pathname));

      // Build response
      const headers = new Headers(resForClient.headers);
      Object.entries(MINIMAL_SECURITY_HEADERS).forEach(([k, v]) => headers.set(k, v));

      // If origin says no-store but this path is whitelisted, override it
      const originCC = resForClient.headers.get("Cache-Control") || "";
      if (originCC.includes("no-store") && shouldCache(url.pathname)) {
        headers.delete("Cache-Control");
      }

      const ct = resForClient.headers.get("Content-Type") || "";
      if (ct.includes("json") || !ct) headers.set("Content-Type", "application/json; charset=utf-8");
      headers.set("Cache-Control", `public, max-age=${ttl}, stale-while-revalidate=${ttl * 2}`);
      headers.set("Vary", buildVaryHeader(request, headers.get("Vary")));

      const finalResp = new Response(body, {
        status: resForClient.status,
        statusText: resForClient.statusText,
        headers,
      });

      // Fill Edge cache
      ctx.waitUntil(cache.put(cacheReq, finalResp.clone()));
      return finalize(finalResp, "MISS");
    }

    if (originRes.status === 404 || originRes.status === 410) {
      ctx.waitUntil(env.MY_APP_STORAGE.put(negKey(url.pathname), "1", { expirationTtl: NEG_TTL_SECS }));
      console.log(`Negative cache set for: ${url.pathname}`);
    }

    // Pass-through (non-cacheable) with security headers
    const headers = new Headers(resForClient.headers);
    Object.entries(MINIMAL_SECURITY_HEADERS).forEach(([k, v]) => headers.set(k, v));

    const passResp = new Response(resForClient.body, {
      status: resForClient.status,
      statusText: resForClient.statusText,
      headers,
    });

    return finalize(passResp, "MISS-NOCACHE");
  },
};
