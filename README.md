# Notch for Windows

Snippy, the cloud assistant that used to live in Notch, is now a separate app: https://github.com/Shhhhleo/snippy

A local, customisable notch at the centre of the top edge of a selected display. Built with Python and native Qt widgets. Hover to expand, move away to collapse. Windows 10/11 x64.

## Run

Open `dist/Notch/Nook/Nook.exe`, or double-click `launch.cmd`. Keep the entire `dist/Notch/Nook` folder together. Quit an older running copy first using its tray menu. Right-click the notch or use its tray icon to open Settings or quit. Double-click the tray icon to open Settings. Escape collapses the notch. The default resting strip is 700 × 42 logical pixels; hovering opens an 840 × 132 music/calendar panel. The resting strip keeps the current or paused track and clock visible. Leaving collapses even when a search field has focus; applying a template no longer pins the panel open. With no track available, the music section disappears and the first two enabled non-music widgets fill the space. Drag the widget order in Settings to choose this idle layout. Expansion takes 150 ms; contraction takes 120 ms after a default 90 ms leave delay. Preview restores the resting notch.

## Appearance templates

Settings → Appearance offers Everyday, Focus and Studio presets. One click applies the sizes and previews the notch. Fine-tuning is hidden until requested. Import or save a `.json` template to share an appearance. Downloadable copies are in `templates/` in this repository, accessible through the Template downloads button (GitHub sign-in is required for this private repository). Templates contain only validated appearance values, never account credentials or personal data. They cannot execute code. Existing original default dimensions are migrated to the new compact layout.

Clock tiles offer Numeral, Analog, Bold analog, World row and World grid faces through the Desktop gallery and each tile’s Clock face menu. World clocks use timezone data for daylight-saving changes. Music uses a vinyl record presentation and Notes have ruled lines.

## Desktop widgets

Settings → Desktop adds individual Clock, Music, To do, Weather, Calendar, Note and Photo tiles, or a ready-made three-tile layout. Tiles have no headings. Drag their outer margin; hover to reveal the ··· menu, or right-click. The menu changes Glass, Paper or Midnight style, locks positions, or removes the widget. Positions, tasks, notes and photo choices persist locally. Tiles sit behind normal application windows and are independent of notch expansion. Glass uses transparency, not an operating-system blur effect. Desktop behaviour after Explorer restarts, Show Desktop, or virtual-desktop changes has not been validated.

Music and tasks share data with the notch. Weather uses a configured city or Windows location. Celsius/Fahrenheit buttons are on the widget. Forecasts come from Open-Meteo; this is not the Windows Weather app’s forecast feed. Calendar shows imported deadlines for today and upcoming connected Google Calendar events. Photo tiles crop images to fill a rounded frame. Once a photo is chosen, change it through the widget menu. A maximum of 20 desktop tiles prevents accidental unbounded creation.

## Features and connection status

| Widget | Implementation |
| --- | --- |
| Music | Windows media sessions, artwork, player selection, previous/next, play/pause and off/playlist/song repeat. Controls depend on support exposed by the player. |
| Time | Local time, installed font selection, three layouts, seconds and 24-hour options. |
| To do | Add, complete and delete tasks with local persistence. |
| Files | Cancellable filename search in a selected folder, up to 50 results or 8 seconds. Double-click or Enter opens a file. Dependency and system folders are skipped. |
| Weather | Windows location or city selection, Open-Meteo forecasts, on-widget Celsius/Fahrenheit controls. Windows location permission is required; no direct Windows Weather forecast API is used. |
| Google Calendar | Browser sign-in with OAuth PKCE and loopback callback, primary calendar upcoming events. Requires a Google Desktop OAuth client and enabled Calendar API. |
| Stocks | Up to eight user-chosen Finnhub symbols, quote timestamps, user-supplied API key. Availability and delays depend on the provider. |
| Claude usage | Live session and weekly plan limits with reset times, refreshed every minute or on click. Uses the Claude Code sign-in in `~/.claude/.credentials.json` and refreshes its token when expired. Also a desktop tile (orange rings). |
| Codex usage | Opens the official usage page. OpenAI documents Codex Compliance API usage for eligible workspaces; personal-plan usage is shown in ChatGPT/Codex settings. |
| Running tasks | Local Claude, Codex, ChatGPT and terminal process presence. Agent task status/completion is pending. |
| Calls | WhatsApp, Zoom and Instagram launch links. Live call state, mute and hang-up integration is pending. |
| Academia | Opens the account dashboard in the user's browser and imports local deadline JSON. Authenticated automatic sync is pending a supported Academia API. |

Settings support widget selection and drag ordering, display, expanded and collapsed dimensions, opacity, radius, clock font, accent, animation and collapse delay. The selected display's full bounds determine top-centre placement, including high-DPI logical coordinates. Multi-display hardware behaviour needs further testing.

## Accounts and data

Settings and tasks reside in `%LOCALAPPDATA%/Nook/settings.json`. Tokens and Google client secrets use Windows DPAPI encryption in `accounts.bin`, bound to the signed-in Windows user. Nothing is uploaded by file search. Weather sends the configured city or rounded Windows coordinates to Open-Meteo. Enabled account widgets contact their respective providers. There is no analytics service.

In Settings → Connections, add a Finnhub API key and comma-separated symbols. Google requires the client ID and optional client secret from a Desktop OAuth application. Save, then select Connect Google Calendar. User consent happens in the default browser. Disconnect removes local Google tokens; revoke server-side grants through Google account settings if required.

Academia import accepts an array of objects, each with `title` and an ISO date/time `due`, for example `[ { "title": "Essay", "due": "2026-12-01T17:00:00+05:30" } ]`. Imports are snapshots and replace the previous imported list. A browser login alone does not connect deadlines to Notch.

## Development

```powershell
python -m venv .venv
python -m pip --python .venv/Scripts/python.exe install -r requirements.txt pyinstaller
.venv/Scripts/python.exe main.py --settings
.venv/Scripts/python.exe -m unittest discover -s tests -v
./build.ps1
```

The portable build bundles its runtime. No Python installation is needed to run the built app. Qt Essentials avoids a web engine. Media polls every 1.5 seconds, other network widgets every five minutes, and process presence every fifteen seconds while expanded. Media calls have an eight-second timeout. File search runs only after input and cancels when replaced. Networking and search use a bounded worker pool.

## Integration references

- [Windows media session controls](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession)
- [Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Open-Meteo](https://open-meteo.com/en/docs)
- [Finnhub](https://finnhub.io/docs/api/quote)
- [Microsoft settings guidelines](https://learn.microsoft.com/en-us/windows/apps/design/app-settings/guidelines-for-app-settings)

This is an initial desktop implementation. Provider-backed account integrations require credentials and live account validation. The portable executable is unsigned.

See `VALIDATION.md` for test coverage and remaining hardware/account checks.

Builds update the existing `dist/Notch/Nook` folder. The build stages binaries under `build/package`. Close Notch through its tray menu before replacing a running executable. The build does not stop an existing app or make another version-named distribution folder.
