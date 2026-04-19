# LibreLinkUp Desktop v1.0.9

Windows desktop app for monitoring CGM glucose readings from a FreeStyle Libre sensor via Abbott's unofficial LibreLinkUp API.

## Tech Stack
Python 3.13 · PySide6 (Qt) · pyqtgraph · requests · cryptography (Fernet) · packaging · PyInstaller

## Structure
- `main.py` — Entry point, AppUserModelID, `__version__`, `app_title()` helper
- `api/client.py` — Login, connections, graph, logbook API calls
- `api/models.py` — Dataclasses: GlucoseReading, Connection, GraphData, LogbookEntry
- `ui/login_window.py` — Login dialog with region dropdown + remember credentials
- `ui/main_window.py` — Glucose display, chart, taskbar icon, beep alerts, compact view, gear menu, always-on-top
- `ui/graph_widget.py` — pyqtgraph chart with target band, alarm lines, time axis
- `ui/logbook_dialog.py` — Logbook table dialog
- `utils/updater.py` — Auto-update: check GitHub Releases, download zip, apply via batch script
- `utils/config.py` — JSON config with Fernet-encrypted credentials
- `resources/style.qss` — Qt stylesheet (red/white theme)
- `config.json` — User-editable defaults (lives next to exe or main.py)
- `VERSION` — Version string (1.0.9)
- `docs/index.html` — Web version: single-page app (hosted on GitHub Pages)
- `docs/worker.js` — Cloudflare Worker CORS proxy (deployed separately)
- `docs/README.md` — Web version setup guide

## API
Base: `https://api-{region}.libreview.io` (regions: us, ca, eu, de, fr, au, jp)
Headers: `product: llu.android`, `version: 4.16.0` (server-enforced minimum)
Auth: `POST /llu/auth/login` → JWT (may redirect to correct region)
Data: `GET /llu/connections`, `/connections/{id}/graph` (15-min intervals, 12h), `/connections/{id}/logbook`
Auth headers: `Authorization: Bearer {token}` + `Account-Id: sha256(user_id)`

## Key Behaviors
- Auto-login: skips login screen when cached credentials are valid
- Gear menu (⚙): compact/full toggle, keep on top, beep settings, check for updates, logout
- Accumulates 1-min readings locally to fill API's 15-min graph gaps
- Stale data (>`stale_minutes`): alternates value / "No Recent Data" at 800ms
- Taskbar icon: 256px rounded rect, 4-tier color scheme by mmol/L range (<4 red/yellow, 4–10 green/black, 10.1–14.9 yellow/black, 15+ dark red/white); when stale, flashes between last reading and grey "--" at 800ms
- Warning beep: 1000Hz 600ms via `winsound.Beep` when below threshold
- Trend arrows: 1=down 2=↘ 3=→ 4=↗ 5=up
- Unit conversion: `ValueInMgPerDl / 18.0` = mmol/L
- Compact view: glucose + trend only, toggled via gear menu, persisted in config
- Always on top: `WindowStaysOnTopHint`, toggled via gear menu, persisted in config
- Window position: saved on close, restored on start; centers on screen when expanding from compact to full
- Auto-update: background thread checks GitHub Releases API for newer version on startup and every hour; if found, downloads `LibreLinkUp.zip`, spawns a `.bat` updater script (timeout → Expand-Archive → relaunch), and exits; manual "Check for Updates..." in gear menu prompts before applying
- Prevent sleep: blocks screensaver and display sleep via `SetThreadExecutionState`; controlled by `prevent_sleep` config key (default `true`)
- Logout clears cached credentials so next launch shows login screen
- Version in window titles via `app_title(config, suffix)` — hidden `hide_version` config key suppresses it

## Web Version
- Hosted on GitHub Pages at `https://jakeiiiii.github.io/LibreLinkUp-desktop/`
- CORS proxy via Cloudflare Worker at `https://llu-proxy.jake-c67.workers.dev`
- Single-page app in `docs/index.html` — Chart.js chart, Web Audio API beep, AES-GCM encrypted credentials in localStorage
- Worker code in `docs/worker.js` — whitelists LibreLinkUp API hosts, forwards requests, adds CORS headers
- No backend needed; worker runs on Cloudflare free tier (100k requests/day)
- "Remember credentials" defaults to on. When cached creds are present, an inline `<head>` script sets `html[data-auto-login]` synchronously so the login screen never paints; `DOMContentLoaded` then calls `doLogin()`. On any failure (`abortAutoLogin()`) the attribute is removed and the login screen reappears. Without cached creds, the form pre-fills but the user must click Login (avoids TV-browser checkbox-toggle triggering login)
- Stale data on web does NOT blink (unlike desktop). Last value stays visible with `.stale` class (muted color); steady display preferred for TV viewing
- `#readingTime` shows the current wall-clock time (not the reading timestamp), updated every 60s via `clockTimer`. The bottom bar's "Updated …" label still shows the last successful refresh time
- Info-bar glucose number, trend arrow, and time use `clamp(…, vw, …)` font sizing so the row fits on both phones and TVs; `white-space: nowrap` keeps each span on one line
- Dark/light theme respects `prefers-color-scheme`. All surface/text/border colors are CSS variables (`--bg`, `--text`, `--card-bg`, `--hover-bg`, `--input-border`, `--chart-line`, `--chart-grid`, `--glucose-normal`, `--glucose-high-severe`, `--shadow`) with a dark-mode `@media` block overriding them. JS reads vars via `themeVar()` for Chart.js line/grid/tick colors and for `glucoseColor()`. `applyTheme()` hooks `matchMedia("(prefers-color-scheme: dark)").change` so live OS theme toggles re-paint the chart without reload
- No-signal indicator: `#signalIndicator` in the bottom bar (`● No signal`, 12px muted, opacity 0.75) is hidden on success and shown on fetch failure; the last successful "Updated …" label is preserved so the user still sees when the data was last good
- TV-safe padding on `#appScreen` via `max(env(safe-area-inset-*), 3vw/2vh)` keeps content inside the overscan area

## Build
```
pip install -r requirements.txt
python main.py            # dev run
build.bat                 # PyInstaller → dist/LibreLinkUp/LibreLinkUp.exe
cleanup.bat               # remove build/, dist/, __pycache__, .pyc, .spec
```

## Workflow Prompts

### Commit only (no release)
When the user says: **"commit and push"**
- Commit and push changes. Do NOT bump the version, tag, or create a GitHub Release.

### Cut a new release
When the user says: **"release"**
- Bump to the next patch version (e.g. 1.0.6 → 1.0.7)
- Update version everywhere: `utils/version.py`, `VERSION`, `README.md`, `CLAUDE.md`
- Rebuild `bin/LibreLinkUp.zip` via PyInstaller + Compress-Archive
- Commit and push all changes
- Create git tag (e.g. `v1.0.7`) and push it
- Create a GitHub Release with `bin/LibreLinkUp.zip` attached
