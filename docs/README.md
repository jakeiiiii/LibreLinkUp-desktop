# LibreLinkUp Web

Browser-based glucose monitor that mirrors the desktop app. Hosted for free on GitHub Pages with a Cloudflare Worker as a CORS proxy.

## Setup

### 1. Deploy the Cloudflare Worker (CORS proxy)

The LibreLinkUp API doesn't allow browser requests directly (CORS), so a tiny proxy is needed.

1. **Create a free Cloudflare account** at [dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up) (no credit card required)
2. Go to **Workers & Pages** in the left sidebar
3. Click **Create** → **Create Worker**
4. Give it a name (e.g. `llu-proxy`)
5. Click **Deploy** (deploys the default "Hello World")
6. Click **Edit Code**
7. Replace all the code with the contents of [`worker.js`](worker.js)
8. Click **Deploy**

You'll get a URL like: `https://llu-proxy.your-name.workers.dev`

**Free tier:** 100,000 requests/day — more than enough for personal use (~1,440 requests/day at 1-minute polling).

### 2. Enable GitHub Pages

1. Go to your repo **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/web`
4. Save

Your app will be live at: `https://yourusername.github.io/LibreLinkUp-desktop/`

### 3. Use the web app

1. Open the GitHub Pages URL
2. Paste your Cloudflare Worker URL in the **Worker URL** field
3. Select your region, enter your LibreLinkUp email/password
4. Check **Remember credentials** to stay logged in (credentials are AES-256 encrypted in localStorage)
5. Click **Login**

## Features

- Real-time glucose display with trend arrows
- 12-hour chart with target range band and alarm lines
- Logbook view
- Unit toggle (mmol/L ↔ mg/dL)
- Low glucose beep alert (Web Audio API)
- Stale data: alternates between the last value and "No Recent Data" every 800ms (matches desktop)
- Encrypted credential storage in localStorage (AES-GCM via Web Crypto API)
- "Remember credentials" defaults to on. When cached, the login screen is skipped entirely on next visit and the app loads directly. Without cached credentials, the form is shown and the user clicks Login.
- Auto-refresh every 60 seconds
- TV-safe layout: viewport-based padding keeps content inside the overscan area on TV browsers
- Responsive info-bar: glucose value, trend arrow, and clock scale via `clamp()` so everything fits on phones and TVs alike
- Dark/light theme follows the OS (`prefers-color-scheme`); live switches re-paint the chart without a reload
- Subtle no-signal indicator: small muted `● No signal` appears in the bottom bar when a refresh fails, while the last successful "Updated …" time stays visible

## Architecture

```
Browser (GitHub Pages)          Cloudflare Worker           LibreLinkUp API
─────────────────────  ──→  ─────────────────────  ──→  ─────────────────────
  index.html (static)         worker.js (proxy)         api-{region}.libreview.io
  localStorage (creds)        Adds CORS headers
                              Forwards all requests
```

## Security

- Credentials are encrypted with AES-256-GCM (PBKDF2-derived key) before being stored in localStorage
- The Worker URL is stored in plain text (it's not sensitive)
- The Cloudflare Worker only proxies requests to whitelisted LibreLinkUp API hosts
- All traffic is HTTPS end-to-end
