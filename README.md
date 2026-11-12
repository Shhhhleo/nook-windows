# Nook for Windows

A local, customisable notch at the centre of the top edge of a selected display. Built with Python and native Qt widgets. Hover to expand, move away to collapse, or pin it open. Windows 10/11 x64.

## Run

Open `dist/Snippy/Nook/Nook.exe`, or double-click `launch.cmd`. Keep the entire `dist/Snippy/Nook` folder together. Quit an older running copy first using its tray menu. Right-click the notch or use its tray icon to open Settings or quit. Double-click the tray icon to open Settings. Escape collapses the notch. The default Music panel is 640 × 150 logical pixels. Unpinning returns to the music and calendar view while a song is playing or paused. With no track available, the music section disappears and the first two enabled non-music widgets fill the space. Drag the widget order in Settings to choose this idle layout. An animated cloud companion floats beside the right edge. Expansion takes 150 ms; contraction takes 120 ms after a default 90 ms leave delay. Preview pins the notch open.

## Appearance templates

Settings → Appearance offers Everyday, Focus and Studio presets. One click applies the sizes and previews the notch. Fine-tuning is hidden until requested. Import or save a `.json` template to share an appearance. Downloadable copies are in `templates/` in this repository, accessible through the Template downloads button (GitHub sign-in is required for this private repository). Templates contain only validated appearance values, never account credentials or personal data. They cannot execute code. Existing original default dimensions are migrated to the new compact layout.

Clock tiles offer Numeral, Analog, Bold analog, World row and World grid faces through the Desktop gallery and each tile’s Clock face menu. World clocks use timezone data for daylight-saving changes. Music uses a vinyl record presentation and Notes have ruled lines.

## Desktop widgets

Settings → Desktop adds individual Clock, Music, To do, Weather, Calendar, Note and Photo tiles, or a ready-made three-tile layout. Tiles have no headings. Drag their outer margin; hover to reveal the ··· menu, or right-click. The menu changes Glass, Paper or Midnight style, locks positions, or removes the widget. Positions, tasks, notes and photo choices persist locally. Tiles sit behind normal application windows and are independent of notch pinning. Glass uses transparency, not an operating-system blur effect. Desktop behaviour after Explorer restarts, Show Desktop, or virtual-desktop changes has not been validated.

Music and tasks share data with the notch. Weather needs a city in Connections. Calendar shows imported deadlines for today and upcoming connected Google Calendar events. Photo tiles crop images to fill a rounded frame. Once a photo is chosen, change it through the widget menu. A maximum of 20 desktop tiles prevents accidental unbounded creation.

## Snippy assistant

On first launch, Snippy asks for your name and saves it locally. Change it in Settings → Assistant. Click the small smiling cloud beside the notch to reveal a white quick input. Enter sends your request; a speech bubble shows the reply. The cloud drifts while a request is running and returns beside the notch when it finishes. Open chat enters the blue-sky fullscreen workspace; Escape returns to the desktop. Four exchanges or a reply longer than 500 characters also opens fullscreen. Both views share one conversation.

Fullscreen greetings rotate through casual prompts and the appropriate time greeting: morning 06:00–12:00, afternoon 12:01–16:00, evening 16:01–18:00, and a late-night greeting outside those hours. The name and rotation position persist, while chat messages stay in memory only. After 60 seconds without typing or a running request, Snippy sleeps, slows its animation, and shuts down its owned Ollama service and child processes. A new request starts it again. Disabling animation also disables cloud roaming.

In fullscreen, type a message or press Talk for one Windows speech recognition session, review the recognised text, then Send. Read replies aloud is optional in Settings → Assistant. Voice requires a working default microphone, Windows desktop microphone permission and an installed Windows speech language. Speech input and output run locally. Dictation is bounded by a timeout and never listens continuously.

Without an AI model, these commands already work:

- `24 * 7` or `calculate (25 + 5) / 2` for bounded local arithmetic.
- `find files report` or `find my invoice.pdf` for filename search in the Behaviour search folder. Activate a result to open its containing folder.
- `look up solar energy` or `/web solar energy` for live Wikipedia search results with source links. A button opens a wider search in the browser. This is not a general web crawling service.

Ollama 0.40.16 and qwen3:0.6b are bundled inside the portable app folder. Open the companion and send a message to start local AI automatically. No separate installation or model download is needed by the end user. The service binds to 127.0.0.1:11435 and requests model unloading after each response. The runtime and model significantly increase the distribution size. Small models have limited reasoning quality.

The model can answer or request bounded maths, filename search and Wikipedia tools. A model-proposed online lookup requires pressing the visible lookup button. Explicit `/web` or `look up` commands run directly. No shell execution, file editing, file-content reading or account access is granted to the model. Chat text stays in process memory and clears when the app closes. Public lookup topics go to Wikipedia; filenames and file contents are not uploaded. This is a small assistant, not a full autonomous desktop-control agent.

## Snippy notification alerts

Settings → Assistant → Connect notifications requests Windows notification-listener access. Alerts are off by default. Once allowed, Nook checks for new Windows toast notifications every five seconds, ignores the existing notification-centre backlog, and announces new arrivals through Snippy. Choose all apps or a comma-separated app-name filter. Message previews are optional. The last 20 alerts stay in RAM only and never enter chat history, model prompts, logs or external services. Alerts do not load Ollama. Turn off announcements to stop polling and clear this list.

This covers apps that actually publish Windows notifications, including supported/configured chat apps. It cannot detect silent in-app messages, read chat databases or infer that an AI task finished. Browser notifications may be attributed to the browser. App-specific notification delivery and Windows focus settings still apply.

**Windows setup:** the portable Python process currently reports notification access denied on the development machine. The build includes `AppxManifest.xml`, assets and `Register-Nook.ps1` for optional development registration with the required capability. For this unsigned development build, enable Windows Developer Mode yourself, quit the portable Nook copy, run `Register-Nook.ps1` from the complete built Nook folder in Windows PowerShell, then launch **Nook from Start** and select **Connect notifications**. The helper registers only Nook; it does not enable Developer Mode, modify other apps or grant notification permission. Keep the registered folder in place. This registration path and live cross-app delivery have not yet been validated on this machine; source/UI behaviour is tested with synthetic notifications. A signed production installer remains pending.

References: [Microsoft notification listener](https://learn.microsoft.com/en-us/windows/apps/develop/notifications/app-notifications/notification-listener), [development app registration](https://learn.microsoft.com/en-us/windows/apps/develop/testing/loose-file-registration).

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
./prepare-ai.ps1
./build.ps1
```

The portable build bundles its runtime. No Python installation is needed to run the built app. Qt Essentials avoids a web engine. Media polls every 1.5 seconds, other network widgets every five minutes, and process presence every fifteen seconds while expanded. Media calls have an eight-second timeout. File search runs only after input and cancels when replaced. Networking and search use a bounded worker pool.

## Integration references

- [Windows media session controls](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession)
- [Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Notion search](https://developers.notion.com/reference/post-search)
- [Open-Meteo](https://open-meteo.com/en/docs)
- [Finnhub](https://finnhub.io/docs/api/quote)
- [Ollama local chat API](https://docs.ollama.com/api/chat)
- [Windows single-utterance speech recognition](https://learn.microsoft.com/en-us/dotnet/api/system.speech.recognition.speechrecognitionengine.recognize)
- [MediaWiki search](https://www.mediawiki.org/wiki/API:Search)

This is an initial desktop implementation. Provider-backed account integrations require credentials and live account validation. The portable executable is unsigned.
