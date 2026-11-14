# Notch for Windows

A local, customisable notch at the centre of the top edge of a selected display. Built with Python and native Qt widgets. Hover to expand, move away to collapse. Windows 10/11 x64.

## Run

Open `dist/Snippy/Nook/Nook.exe`, or double-click `launch.cmd`. Keep the entire `dist/Snippy/Nook` folder together. Quit an older running copy first using its tray menu. Right-click the notch or use its tray icon to open Settings or quit. Double-click the tray icon to open Settings. Escape collapses the notch. The default resting strip is 700 × 42 logical pixels; hovering opens an 840 × 132 music/calendar panel. The resting strip keeps the current or paused track and clock visible. Leaving collapses even when a search field has focus; applying a template no longer pins the panel open. With no track available, the music section disappears and the first two enabled non-music widgets fill the space. Drag the widget order in Settings to choose this idle layout. An animated cloud companion floats beside the right edge. Expansion takes 150 ms; contraction takes 120 ms after a default 90 ms leave delay. Preview restores the resting notch.

## Appearance templates

Settings → Appearance offers Everyday, Focus and Studio presets. One click applies the sizes and previews the notch. Fine-tuning is hidden until requested. Import or save a `.json` template to share an appearance. Downloadable copies are in `templates/` in this repository, accessible through the Template downloads button (GitHub sign-in is required for this private repository). Templates contain only validated appearance values, never account credentials or personal data. They cannot execute code. Existing original default dimensions are migrated to the new compact layout.

Clock tiles offer Numeral, Analog, Bold analog, World row and World grid faces through the Desktop gallery and each tile’s Clock face menu. World clocks use timezone data for daylight-saving changes. Music uses a vinyl record presentation and Notes have ruled lines.

## Desktop widgets

Settings → Desktop adds individual Clock, Music, To do, Weather, Calendar, Note and Photo tiles, or a ready-made three-tile layout. Tiles have no headings. Drag their outer margin; hover to reveal the ··· menu, or right-click. The menu changes Glass, Paper or Midnight style, locks positions, or removes the widget. Positions, tasks, notes and photo choices persist locally. Tiles sit behind normal application windows and are independent of notch expansion. Glass uses transparency, not an operating-system blur effect. Desktop behaviour after Explorer restarts, Show Desktop, or virtual-desktop changes has not been validated.

Music and tasks share data with the notch. Weather uses a configured city or Windows location. Celsius/Fahrenheit buttons are on the widget. Forecasts come from Open-Meteo; this is not the Windows Weather app’s forecast feed. Calendar shows imported deadlines for today and upcoming connected Google Calendar events. Photo tiles crop images to fill a rounded frame. Once a photo is chosen, change it through the widget menu. A maximum of 20 desktop tiles prevents accidental unbounded creation.

## Snippy assistant

On first launch a six-step setup asks for your name, display, accent, widgets, weather location/units, cowork folder, voice and notification preferences. Settings → Assistant can run setup again. Optional accounts connect afterwards.

Click the smiling cloud for a small white typing bar. Enter sends; replies appear in a speech bubble. The bar remains available through a conversation. Only the arrow beside the bar opens the blue-sky fullscreen workspace; long replies and repeated exchanges never force it open. Escape returns to the desktop. Drag the cloud onto either display, including monitors with negative coordinates. Its home position persists and is clamped to an available screen after display changes. During work it drifts between displays; playback makes it gently bob and sway. These animations use painted vectors, not video or image sequences.

The fullscreen Chat library stores conversations locally. New chat starts a separate conversation; selecting a saved chat restores it. Delete chat removes it after confirmation. Greetings use the saved user name and time of day. Time, date, user name and assistant identity answers are deterministic; they do not ask the language model.

Enable **Hold Ctrl + Alt to talk** in setup or Settings → Assistant. Hold left Ctrl + Alt, wait for the Listening indicator, speak, and release to send. Snippy speaks the reply. Right Alt is excluded so AltGr typing is not intercepted. Only modifier states are checked; no typed keys or screen content are captured. A one-shot Talk button is also available. Vosk recognition is offline, with bundled US and Indian-English models and a microphone selector in Settings → Assistant. Audio capture starts before the model loads, so initial words are buffered. Low-confidence recognition appears in the typing bar for review. The model is released when Snippy sleeps. Synthetic WAV decoding and press/release transitions are tested; actual microphone recognition and playback still require hardware validation.

Local tools work without loading AI:

- `What time is it?`, `/date`, `What is my name?`, `Who made you?`.
- `24 * 7` or `calculate (25 + 5) / 2`.
- `find files report`, `list files`, `read notes.txt` (within your chosen cowork folder).
- `make a file inventory` prepares a CSV for review.
- `look up solar energy` searches Wikipedia with sources; a button opens wider browser search.

The model can summarise a text file (`summarise notes.txt`) and propose new TXT, Markdown or CSV documents. Snippy also understands natural requests such as `search for my report`, `read the file called notes.txt`, `add task buy milk`, or `mark buy milk done`. File previews are bounded to 250 KB and text types; paths and symlinks outside the chosen search folder are rejected. Creation requires reviewing the proposal; existing files are never overwritten. It cannot run arbitrary commands, code, or control other apps.

Ollama 0.40.16 and **qwen3:1.7b** are bundled. No separate Ollama installation is required. A private service binds to 127.0.0.1:11435. Opening the typing bar preloads the model; normal replies stream as they are generated. Conversation and tool selection use different prompts to reduce spurious tool calls and repetition. After one idle minute, Snippy sleeps and stops its owned AI service to release memory. The first request after sleep may still need a cold load. Small local models can still make factual mistakes; use sources for important or current facts.

### Optional MCP apps

Settings → Connections → **Add or manage MCP apps** offers Notion as an optional preset, plus custom Streamable HTTP endpoints. Add an app, select it, then Connect. OAuth opens the provider’s browser sign-in; bearer tokens are also supported. Credentials are encrypted with Windows DPAPI. Connected tools can be proposed by Snippy in chat or run from the app manager. Every tool call shows its name and arguments for review before sending them to the provider. No account is connected automatically. Live Notion OAuth/account operations still need user sign-in and end-to-end validation; a localhost MCP fixture verifies protocol initialization, tool discovery and execution.

## Snippy notification alerts

Settings → Assistant → Connect notifications requests Windows notification-listener access. Alerts are off by default. Once allowed, Notch checks for new Windows toast notifications every five seconds, ignores the existing notification-centre backlog, and announces new arrivals through Snippy. Choose all apps or a comma-separated app-name filter. Message previews are optional. The last 20 alerts stay in RAM only and never enter chat history, model prompts, logs or external services. Alerts do not load Ollama. Turn off announcements to stop polling and clear this list.

This covers apps that actually publish Windows notifications, including supported/configured chat apps. It cannot detect silent in-app messages, read chat databases or infer that an AI task finished. Browser notifications may be attributed to the browser. App-specific notification delivery and Windows focus settings still apply.

**Windows setup:** the portable Python process currently reports notification access denied on the development machine. The build includes `AppxManifest.xml`, assets and `Register-Nook.ps1` for optional development registration with the required capability. For this unsigned development build, enable Windows Developer Mode yourself, quit the portable Nook copy, run `Register-Nook.ps1` from the complete built Nook folder in Windows PowerShell, then launch **Notch from Start** and select **Connect notifications**. The helper registers only Nook; it does not enable Developer Mode, modify other apps or grant notification permission. Keep the registered folder in place. This registration path and live cross-app delivery have not yet been validated on this machine; source/UI behaviour is tested with synthetic notifications. A signed production installer remains pending.

References: [Microsoft notification listener](https://learn.microsoft.com/en-us/windows/apps/develop/notifications/app-notifications/notification-listener), [development app registration](https://learn.microsoft.com/en-us/windows/apps/develop/testing/loose-file-registration).

## Features and connection status

| Widget | Implementation |
| --- | --- |
| Music | Windows media sessions, artwork, player selection, previous/next, play/pause and off/playlist/song repeat. Controls depend on support exposed by the player. |
| Time | Local time, installed font selection, three layouts, seconds and 24-hour options. |
| To do | Add, complete and delete tasks with local persistence. |
| Files | Cancellable filename search in a selected folder, up to 50 results or 8 seconds. Double-click or Enter opens a file. Dependency and system folders are skipped. |
| Weather | Windows location or city selection, Open-Meteo forecasts, on-widget Celsius/Fahrenheit controls. Windows location permission is required; no direct Windows Weather forecast API is used. |
| MCP apps | Optional Notion and custom Streamable HTTP apps, OAuth/token connection, tool discovery and reviewed calls. |
| Google Calendar | Browser sign-in with OAuth PKCE and loopback callback, primary calendar upcoming events. Requires a Google Desktop OAuth client and enabled Calendar API. |
| Stocks | Up to eight user-chosen Finnhub symbols, quote timestamps, user-supplied API key. Availability and delays depend on the provider. |
| Claude / Codex usage | Opens the official usage page. Notch does not read personal-plan allowance values. OpenAI documents Codex Compliance API usage for eligible workspaces; personal-plan usage is shown in ChatGPT/Codex settings. |
| Running tasks | Local Claude, Codex, ChatGPT and terminal process presence. Agent task status/completion is pending. |
| Calls | WhatsApp, Zoom and Instagram launch links. Live call state, mute and hang-up integration is pending. |
| Academia | Opens the account dashboard in the user's browser and imports local deadline JSON. Authenticated automatic sync is pending a supported Academia API. |

Settings support widget selection and drag ordering, display, expanded and collapsed dimensions, opacity, radius, clock font, accent, animation and collapse delay. The selected display's full bounds determine top-centre placement, including high-DPI logical coordinates. Multi-display hardware behaviour needs further testing.

## Accounts and data

Settings and tasks reside in `%LOCALAPPDATA%/Nook/settings.json`. Tokens and Google client secrets use Windows DPAPI encryption in `accounts.bin`, bound to the signed-in Windows user. Nothing is uploaded by file search. Weather sends the configured city or rounded Windows coordinates to Open-Meteo. Chat history is stored locally in `chats.sqlite3`; only library titles and the active conversation are loaded into memory. File contents used for summaries stay with the local model. Reviewed MCP tool arguments are sent to the selected app provider. Enabled account widgets contact their respective providers. There is no analytics service.

In Settings → Connections, add optional MCP apps such as Notion, or add a Finnhub API key and comma-separated symbols. Google requires the client ID and optional client secret from a Desktop OAuth application. Save, then select Connect Google Calendar. User consent happens in the default browser. Disconnect removes local Google tokens; revoke server-side grants through Google account settings if required.

Academia import accepts an array of objects, each with `title` and an ISO date/time `due`, for example `[ { "title": "Essay", "due": "2026-12-01T17:00:00+05:30" } ]`. Imports are snapshots and replace the previous imported list. A browser login alone does not connect deadlines to Notch.

## Development

```powershell
python -m venv .venv
python -m pip --python .venv/Scripts/python.exe install -r requirements.txt pyinstaller
.venv/Scripts/python.exe main.py --settings
.venv/Scripts/python.exe -m unittest discover -s tests -v
./prepare-ai.ps1
.venv/Scripts/python.exe prepare-speech.py
./build.ps1
```

The portable build bundles its runtime. No Python installation is needed to run the built app. Qt Essentials avoids a web engine. Media polls every 1.5 seconds, other network widgets every five minutes, and process presence every fifteen seconds while expanded. Media calls have an eight-second timeout. File search runs only after input and cancels when replaced. Networking and search use a bounded worker pool.

## Integration references

- [Windows media session controls](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession)
- [Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Notion MCP](https://developers.notion.com/guides/mcp/overview)
- [Open-Meteo](https://open-meteo.com/en/docs)
- [Finnhub](https://finnhub.io/docs/api/quote)
- [Ollama local chat API](https://docs.ollama.com/api/chat)
- [Vosk offline speech models](https://alphacephei.com/vosk/models)
- [Microsoft settings guidelines](https://learn.microsoft.com/en-us/windows/apps/design/app-settings/guidelines-for-app-settings)
- [MediaWiki search](https://www.mediawiki.org/wiki/API:Search)

This is an initial desktop implementation. Provider-backed account integrations require credentials and live account validation. The portable executable is unsigned.

Performance check (13 November 2026, isolated local service): Qwen 1.7B loaded in 2.91 seconds and answered three short conversation prompts in 1.24, 0.54 and 0.90 seconds. These are single-run observations, not guarantees. Qwen 3.5 0.8B was also tried but its cold response was much slower, so it is not bundled. Clock/name/math bypass model loading. See `VALIDATION.md` for test coverage and remaining hardware/account checks.

Builds update the existing `dist/Snippy/Nook` folder. The build stages binaries under `build/package` and copies only the selected model into the distribution. Close Notch through its tray menu before replacing a running executable. The build does not stop an existing app or make another version-named distribution folder.


## Latest interface and current affairs

Settings now uses left navigation with grouped controls. Desktop → Reference desk adds the dark battery rings, bold square numeral clock, blue forecast and wide split calendar from the supplied reference. Graphite is also available per tile. Empty battery rings mean unconnected devices; only the PC battery is currently measured. Completed tasks disappear immediately from both surfaces, with their completed records retained locally. Clicking Snippy dismisses the response bubble; the typing bar remains available. New prompts show new replies.

News updates fetch BBC World and Technology feeds every 15 minutes while enabled, and on demand when stale. News questions bypass model memory and show headlines with publication/retrieval times and source links. This is a bounded current-affairs feed, not universal real-time knowledge or continual model training. Unavailable feeds and stale cached results are labelled; unmatched topics are reported as unverified. Disable refresh in Settings → Assistant to stop news network requests. News is cached locally; private chats and files are never included in feed requests.

Visible branding is Notch; the cloud assistant is Snippy. Existing Nook.exe, internal package, data folder and Windows identity stay unchanged to preserve installations and preferences. The speech preparation script downloads official Apache-2.0 Vosk models and records observed SHA-256 hashes in vendor/speech/sources.json; the hashes are provenance records, not separately published signatures. Distribution excludes the downloaded ZIP archives.
