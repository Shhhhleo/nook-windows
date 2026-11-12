# Connect Snippy to Windows notifications

Snippy's local chat and widgets work without this optional setup. Notifications need Windows app identity and the user's notification-listener permission. The plain portable process reported **Denied** during development.

This is an unsigned development build. Its registration helper is included, but registration and real cross-app delivery have not yet been verified on this PC.

1. Keep this complete Nook folder in a permanent location.
2. Enable **Developer Mode** in Windows Settings → For developers if you choose to use development registration. The helper will not change that setting.
3. Quit any running Nook copy using its tray menu.
4. Open Windows PowerShell in this folder and run `./Register-Nook.ps1`.
5. Open **Nook from the Start menu**, then Settings → Assistant → **Connect notifications** and allow the Windows prompt.

The helper registers only this Nook application. It does not grant notification permission or alter other apps. If permission was previously denied, use Windows Settings → Privacy & security → Notifications to review access. A signed production installer is not yet supplied.

Snippy only sees notifications that apps actually send to Windows. Silent messages inside Claude, ChatGPT, WhatsApp, Slack, Zoom or other apps cannot be detected this way. The existing notification-centre backlog is ignored. Message previews are off by default; enable them in Assistant settings if wanted. Alerts stay in RAM and are never sent to the AI model.

[Microsoft notification-listener documentation](https://learn.microsoft.com/en-us/windows/apps/develop/notifications/app-notifications/notification-listener)
