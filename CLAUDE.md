# LibreLinkUp Desktop v1.0.8

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
- `VERSION` — Version string (1.0.8)

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
- Taskbar icon: 256px rounded rect, 4-tier color scheme by mmol/L range (<4 red/yellow, 4–10 green/black, 10.1–14.9 yellow/black, 15+ dark red/white), grey "--" when stale
- Warning beep: 1000Hz 600ms via `winsound.Beep` when below threshold
- Trend arrows: 1=down 2=↘ 3=→ 4=↗ 5=up
- Unit conversion: `ValueInMgPerDl / 18.0` = mmol/L
- Compact view: glucose + trend only, toggled via gear menu, persisted in config
- Always on top: `WindowStaysOnTopHint`, toggled via gear menu, persisted in config
- Window position: saved on close, restored on start; centers on screen when expanding from compact to full
- Auto-update: on startup, background thread checks GitHub Releases API for newer version; if found, downloads `LibreLinkUp.zip`, spawns a `.bat` updater script (timeout → Expand-Archive → relaunch), and exits; manual "Check for Updates..." in gear menu prompts before applying
- Logout clears cached credentials so next launch shows login screen
- Version in window titles via `app_title(config, suffix)` — hidden `hide_version` config key suppresses it

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
