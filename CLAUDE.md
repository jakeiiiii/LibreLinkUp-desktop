# LibreLinkUp Desktop v1.0.3

Windows desktop app for monitoring CGM glucose readings from a FreeStyle Libre sensor via Abbott's unofficial LibreLinkUp API.

## Tech Stack
Python 3.13 · PySide6 (Qt) · pyqtgraph · requests · cryptography (Fernet) · PyInstaller

## Structure
- `main.py` — Entry point, AppUserModelID, `__version__`, `app_title()` helper
- `api/client.py` — Login, connections, graph, logbook API calls
- `api/models.py` — Dataclasses: GlucoseReading, Connection, GraphData, LogbookEntry
- `ui/login_window.py` — Login dialog with region dropdown + remember credentials
- `ui/main_window.py` — Glucose display, chart, taskbar icon, beep alerts, compact view, gear menu, always-on-top
- `ui/graph_widget.py` — pyqtgraph chart with target band, alarm lines, time axis
- `ui/logbook_dialog.py` — Logbook table dialog
- `utils/config.py` — JSON config with Fernet-encrypted credentials
- `resources/style.qss` — Qt stylesheet (red/white theme)
- `config.json` — User-editable defaults (lives next to exe or main.py)
- `VERSION` — Version string (1.0.3)

## API
Base: `https://api-{region}.libreview.io` (regions: us, ca, eu, de, fr, au, jp)
Headers: `product: llu.android`, `version: 4.16.0` (server-enforced minimum)
Auth: `POST /llu/auth/login` → JWT (may redirect to correct region)
Data: `GET /llu/connections`, `/connections/{id}/graph` (15-min intervals, 12h), `/connections/{id}/logbook`
Auth headers: `Authorization: Bearer {token}` + `Account-Id: sha256(user_id)`

## Key Behaviors
- Auto-login: skips login screen when cached credentials are valid
- Gear menu (⚙): compact/full toggle, keep on top, beep settings, logout
- Accumulates 1-min readings locally to fill API's 15-min graph gaps
- Stale data (>`stale_minutes`): alternates value / "No Recent Data" at 800ms
- Taskbar icon: 256px rounded rect, bg green/orange/red by range, grey "--" when stale
- Warning beep: 1000Hz 600ms via `winsound.Beep` when below threshold
- Trend arrows: 1=down 2=↘ 3=→ 4=↗ 5=up
- Unit conversion: `ValueInMgPerDl / 18.0` = mmol/L
- Compact view: glucose + trend only, toggled via gear menu, persisted in config
- Always on top: `WindowStaysOnTopHint`, toggled via gear menu, persisted in config
- Window position: saved on close, restored on start; centers on screen when expanding from compact to full
- Logout clears cached credentials so next launch shows login screen
- Version in window titles via `app_title(config, suffix)` — hidden `hide_version` config key suppresses it

## Build
```
pip install -r requirements.txt
python main.py            # dev run
build.bat                 # PyInstaller → dist/LibreLinkUp/LibreLinkUp.exe
cleanup.bat               # remove build/, dist/, __pycache__, .pyc, .spec
```
