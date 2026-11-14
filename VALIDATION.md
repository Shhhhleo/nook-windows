# Notch update validation — 14 November 2026

_Recorded before Snippy moved to its own repository; Snippy, MCP, speech and AI items below now belong to the Snippy project._

- 30 regression tests passed: hover/collapse, paused media, idle widget substitution, persistent preferences and chats, deterministic clock/name/identity, bounded file access and exclusive document creation, unit conversion requests, notification filtering, and simulated display positioning.
- MCP test server on an ephemeral loopback port exercised initialize, tools/list and tools/call. No account or external application was accessed by the tests.
- Qt layouts were rendered offscreen with fixture content: resting/expanded notch, compact chat, fullscreen chat and onboarding. No desktop capture or mouse/keyboard control was used.
- Offline Vosk speech capture buffering and Ctrl+Alt transitions were tested with injected audio/modifier states. A synthetic WAV was decoded by both bundled models without microphone access or playback: US model exact; Indian-English model made a minor wording error on the US synthetic voice. Low-confidence text requires review. Offscreen tests disable key polling.
- Isolated Qwen 1.7B trial: 2.91 s preload; short responses 1.24/0.54/0.90 s. Follow-up selected the preceding suggestion correctly. Model factual accuracy is not guaranteed by these samples.
- Packaged executable stayed running offscreen for eight seconds with no logged exceptions. The distribution's bundled runtime listed Qwen 1.7B and generated a response on an isolated port. A model-generated introduction confused the app and assistant names; common introduction requests now use the same deterministic identity handler as name questions.

Still requires live validation: actual dual-monitor/DPI dragging and display disconnects, microphone recognition/playback, Windows location permission, Notion OAuth and account operations, and cross-app notification delivery. The portable app is unsigned. Windows Weather does not supply this app's forecast; Open-Meteo supplies forecasts using city or Windows location.

- News tests cover cache reuse, live versus stale labels, topic misses and model bypass. Live BBC feed retrieval returned five dated source links. No private data was transmitted.
- Updated offscreen previews cover Settings navigation and grouped controls, dark reference tiles, compact/expanded notch and Snippy bubble. Completing a task and clicking away a response have regression coverage.
- Final 14 November build updated `dist/Snippy/Nook` successfully after the user quit the running app. Staged and installed executable SHA-256 hashes match. Both Vosk models, libvosk and PortAudio DLLs are present. Total distribution size: 3.67 GiB, including local AI runtime/model and offline dictation.
- Final executable remained running offscreen for eight seconds with no logged exceptions. Idle working set: 82.4 MiB; private memory: 45.2 MiB. These are single-run offscreen startup measurements without loaded AI/speech models, not peak usage guarantees. Final full suite: 30 tests passed in 6.398 seconds.
