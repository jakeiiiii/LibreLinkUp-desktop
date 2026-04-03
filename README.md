# LibreLinkUp Desktop v1.0.0

A Windows desktop app that replicates Abbott's [LibreLinkUp](https://www.librelinkup.com/) Android app, letting you monitor FreeStyle Libre CGM glucose readings directly on your PC -- no Android emulator needed.

![Screenshot](screenshot.png)

## Features

- **Real-time glucose monitoring** with auto-refresh
- **12-hour glucose chart** with target range band and alarm lines
- **Dynamic taskbar icon** showing current glucose number (color-coded green/orange/red)
- **Compact view** -- just the glucose number and trend arrow
- **Warning beep** when glucose drops below a configurable threshold
- **Stale data detection** -- alternates between last reading and "No Recent Data"
- **Logbook** viewer for manual scan history
- **Encrypted credentials** stored locally using Fernet (tied to your Windows user)
- **mmol/L and mg/dL** unit toggle
- **Multi-region support** (US, Canada, EU, Germany, France, Australia, Japan)

## Quick Start

### Option 1: Run from source

```bash
pip install -r requirements.txt
python main.py
```

### Option 2: Build a standalone .exe

```bash
pip install -r requirements.txt
pyinstaller --noconfirm --onedir --windowed --name "LibreLinkUp" --add-data "resources;resources" --add-data "config.json;." main.py
```

The output in `dist/LibreLinkUp/` is self-contained -- copy the folder anywhere and run `LibreLinkUp.exe`. No Python installation required.

## Configuration

Edit `config.json` (next to `main.py` or `LibreLinkUp.exe`):

```json
{
  "region": "Canada",
  "unit": "mmol",
  "refresh_seconds": 60,
  "stale_minutes": 15,
  "low_beep_enabled": true,
  "low_beep_threshold_mmol": 4.0,
  "compact_view": false,
  "remember_credentials": false
}
```

| Setting | Description |
|---------|-------------|
| `region` | API region: US, Canada, EU, Germany, France, Australia, Japan |
| `unit` | `"mmol"` or `"mgdl"` |
| `refresh_seconds` | How often to poll the API (seconds) |
| `stale_minutes` | Minutes before a reading is considered stale |
| `low_beep_enabled` | Enable/disable the low glucose warning beep |
| `low_beep_threshold_mmol` | Beep when glucose is below this value (mmol/L) |
| `compact_view` | Start in compact mode (number + trend only) |
| `remember_credentials` | Save encrypted login credentials |

### Hidden Settings

These settings are not exposed in the UI. Add them manually to `config.json` if needed.

| Setting | Description |
|---------|-------------|
| `hide_version` | `true` to hide the version number from window titles (default: `false`) |

## Requirements

- Windows 10/11
- A [LibreLinkUp](https://www.librelinkup.com/) account with an active connection to a FreeStyle Libre sensor
- Python 3.10+ (only if running from source)

## How It Works

This app uses the unofficial LibreLinkUp API (the same one Abbott's Android app uses) to fetch glucose data. It requires your LibreLinkUp email and password to authenticate.

**Important:** This is an unofficial project. It is not affiliated with or endorsed by Abbott. The API may change at any time.

## License

MIT
