/**
 * Cloudflare Worker — CORS proxy for LibreLinkUp API
 *
 * Deploy: Cloudflare Dashboard → Workers & Pages → Create Worker → paste this → Deploy
 *
 * Usage from the web app:
 *   fetch("https://<worker>.workers.dev/llu/auth/login", { method: "POST", ... })
 *
 * The worker forwards requests to the LibreLinkUp API region specified
 * in the X-Region header (default: api-ca.libreview.io).
 */

const ALLOWED_HOSTS = [
  "api.libreview.io",
  "api-us.libreview.io",
  "api-ca.libreview.io",
  "api-eu.libreview.io",
  "api-de.libreview.io",
  "api-fr.libreview.io",
  "api-au.libreview.io",
  "api-jp.libreview.io",
];

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin || "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Account-Id, X-Region, product, version, cache-control, connection, accept-encoding",
    "Access-Control-Max-Age": "86400",
  };
}

export default {
  async fetch(request) {
    const origin = request.headers.get("Origin") || "*";

    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    const url = new URL(request.url);
    const path = url.pathname + url.search;

    // Determine target API host from X-Region header
    const regionHost = request.headers.get("X-Region") || "api-ca.libreview.io";
    if (!ALLOWED_HOSTS.includes(regionHost)) {
      return new Response(JSON.stringify({ error: "Invalid region" }), {
        status: 400,
        headers: { ...corsHeaders(origin), "Content-Type": "application/json" },
      });
    }

    const targetUrl = `https://${regionHost}${path}`;

    // Forward headers (strip hop-by-hop and browser-specific ones)
    const forwardHeaders = new Headers();
    for (const [key, value] of request.headers) {
      const lower = key.toLowerCase();
      if (["host", "origin", "referer", "x-region", "cf-connecting-ip", "cf-ray", "cf-visitor", "cf-ipcountry"].includes(lower)) continue;
      forwardHeaders.set(key, value);
    }

    // Ensure required LLU headers
    forwardHeaders.set("product", "llu.android");
    forwardHeaders.set("version", "4.16.0");

    const resp = await fetch(targetUrl, {
      method: request.method,
      headers: forwardHeaders,
      body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
    });

    // Return response with CORS headers
    const responseHeaders = new Headers(resp.headers);
    for (const [k, v] of Object.entries(corsHeaders(origin))) {
      responseHeaders.set(k, v);
    }

    return new Response(resp.body, {
      status: resp.status,
      statusText: resp.statusText,
      headers: responseHeaders,
    });
  },
};
