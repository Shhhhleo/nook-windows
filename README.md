# Nook for Windows

A local, customisable notch at the centre of the top edge of a selected display. Built with Python and native Qt widgets. Hover to expand, move away to collapse, or pin it open. Windows 10/11 x64.

## Run

Open `dist/Nook/Nook.exe`, or double-click `launch.cmd`. Keep the entire `dist/Nook` folder together. Right-click the notch or use its tray icon to open Settings or quit. Double-click the tray icon to open Settings. Escape collapses the notch.

## Features and connection status

| Widget | Implementation |
| --- | --- |
| Music | Windows media sessions, artwork, player selection, previous/next, play/pause and off/playlist/song repeat. Controls depend on support exposed by the player. |
| Time | Local time, installed font selection, three layouts, seconds and 24-hour options. |
| To do | Add, complete and delete tasks with local persistence. |
| Files | Cancellable filename search in a selected folder, up to 50 results or 8 seconds. Double-click or Enter opens a file. Dependency and system folders are skipped. |
| Weather | Open-Meteo city search and weather, Celsius/Fahrenheit, compact/detailed layouts. |
| Notion | Read pages shared with a user-supplied integration token. Click a page to open it. |
| Google Calendar | Browser sign-in with OAuth PKCE and loopback callback, primary calendar upcoming events. Requires a Google Desktop OAuth client and enabled Calendar API. |
| Stocks | Up to eight user-chosen Finnhub symbols, quote timestamps, user-supplied API key. Availability and delays depend on the provider. |
| Claude / Codex usage | Account usage page shortcuts. Live subscription limit telemetry is pending. |
| Running tasks | Local Claude, Codex, ChatGPT and terminal process presence. Agent task status/completion is pending. |
| Calls | WhatsApp, Zoom and Instagram launch links. Live call state, mute and hang-up integration is pending. |
| Academia | Opens the account dashboard in the user's browser and imports local deadline JSON. Authenticated automatic sync is pending a supported Academia API. |

Settings support widget selection and drag ordering, display, expanded and collapsed dimensions, opacity, radius, clock font, accent, animation and collapse delay. The selected display's full bounds determine top-centre placement, including high-DPI logical coordinates. Multi-display hardware behaviour needs further testing.

## Accounts and data

Settings and tasks reside in `%LOCALAPPDATA%/Nook/settings.json`. Tokens and Google client secrets use Windows DPAPI encryption in `accounts.bin`, bound to the signed-in Windows user. Nothing is uploaded by file search. Weather sends the configured city to Open-Meteo. Enabled account widgets contact their respective providers. There is no analytics service.

In Settings → Connections, add a Notion integration token and share pages with that integration, or add a Finnhub API key and comma-separated symbols. Google requires the client ID and optional client secret from a Desktop OAuth application. Save, then select Connect Google Calendar. User consent happens in the default browser. Disconnect removes local Google tokens; revoke server-side grants through Google account settings if required.

Academia import accepts an array of objects, each with `title` and an ISO date/time `due`, for example `[ { "title": "Essay", "due": "2026-12-01T17:00:00+05:30" } ]`. Imports are snapshots and replace the previous imported list. A browser login alone does not connect deadlines to Nook.

## Development

```powershell
python -m venv .venv
python -m pip --python .venv/Scripts/python.exe install -r requirements.txt pyinstaller
.venv/Scripts/python.exe main.py --settings
.venv/Scripts/python.exe -m unittest discover -s tests -v
./build.ps1
```

The portable build bundles its runtime. No Python installation is needed to run the built app. Qt Essentials avoids a web engine. Media polls every five seconds, other network widgets every five minutes, and process presence every fifteen seconds while expanded. Media calls have an eight-second timeout. File search runs only after input and cancels when replaced. Networking and search use a bounded worker pool.

## Integration references

- [Windows media session controls](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession)
- [Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Notion search](https://developers.notion.com/reference/post-search)
- [Open-Meteo](https://open-meteo.com/en/docs)
- [Finnhub](https://finnhub.io/docs/api/quote)

This is an initial desktop implementation. Provider-backed account integrations require credentials and live account validation. The portable executable is unsigned.
