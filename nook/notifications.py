"""Permission-gated Windows toast notifications; no screen or message-store scraping."""
import asyncio
from PySide6.QtCore import QObject, QTimer, Signal


def listener():
    from winrt.windows.ui.notifications.management import UserNotificationListener
    return UserNotificationListener.current


def snapshot():
    from winrt.windows.ui.notifications import NotificationKinds
    current = listener()
    if int(current.get_access_status()) != 1:
        raise PermissionError('Windows notification access is unavailable. Connect again in Settings → Assistant.')
    async def read():
        notifications = await asyncio.wait_for(current.get_notifications_async(NotificationKinds.TOAST), 4)
        rows = []
        for item in notifications:
            try:
                app = item.app_info.display_info.display_name
                binding = item.notification.visual.get_binding('ToastGeneric')
                texts = [element.text for element in binding.get_text_elements()] if binding else []
                rows.append({'key': (str(item.id), item.creation_time.isoformat()), 'app': app,
                             'title': (texts[0] if texts else '')[:200],
                             'body': '\n'.join(texts[1:])[:600]})
            except Exception:
                continue  # A dismissed or malformed toast must not discard the rest.
        return rows
    return asyncio.run(read())


class NotificationDelta:
    def __init__(self):
        self.seen = None

    def update(self, rows, apps=''):
        keys = {tuple(row['key']) for row in rows}
        previous, self.seen = self.seen, keys
        if previous is None:
            return []  # Establish a baseline; do not replay the notification centre.
        filters = [part.strip().casefold() for part in apps.split(',') if part.strip()]
        return [row for row in rows if tuple(row['key']) not in previous
                and (not filters or any(part in row['app'].casefold() for part in filters))]


class NotificationMonitor(QObject):
    status_changed = Signal(str)
    access_changed = Signal(bool)

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.delta = NotificationDelta()
        self.status = 'Notifications are off. Connect to allow Snippy to announce new Windows alerts.'
        self.operation = None
        self.preferences = None
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.poll)
        self.access_timer = QTimer(self)
        self.access_timer.setInterval(100)
        self.access_timer.timeout.connect(self.finish_access)
        self.configure()

    def report(self, message):
        self.status = message
        self.status_changed.emit(message)

    def configure(self):
        preferences = (self.owner.store.settings.get('notifications_apps', ''),
                       self.owner.store.settings.get('notifications_preview', False))
        if preferences != self.preferences:
            self.preferences = preferences
            self.delta = NotificationDelta()
            self.owner.cloud.clear_notifications()
        if self.owner.store.settings.get('notifications_enabled'):
            if not self.timer.isActive():
                self.delta = NotificationDelta()
                self.timer.start()
                self.poll()
        else:
            self.timer.stop()
            if self.operation is not None:
                self.operation.cancel()
                self.operation = None
                self.access_timer.stop()
            self.delta = NotificationDelta()
            self.owner.cloud.clear_notifications()
            self.report('Notifications are off.')

    def connect_access(self):
        if self.operation is not None:
            return
        try:
            # This entry point is called by the settings button on the Qt UI thread.
            self.operation = listener().request_access_async()
            self.report('Allow notification access in the Windows prompt.')
            self.access_timer.start()
        except Exception:
            self.failed('Windows could not request notification access. The registered Notch app and notification permission are required.')

    def finish_access(self):
        try:
            if int(self.operation.status) == 0:
                return
            allowed = int(self.operation.get_results()) == 1
            self.operation = None
            self.access_timer.stop()
            if not allowed:
                self.failed('Access not granted. Register the notification-enabled app, then allow access in Windows Settings → Privacy & security → Notifications.')
                return
            self.owner.store.settings['notifications_enabled'] = True
            self.owner.store.save()
            self.access_changed.emit(True)
            self.configure()
            self.report('Connected. Only newly arriving Windows notifications will be announced.')
        except Exception:
            self.operation = None
            self.access_timer.stop()
            self.failed('Notification access failed. Use the registered app and enable Windows notification permission.')

    def poll(self):
        if not self.owner.store.settings.get('notifications_enabled'):
            return
        self.owner.run_job('notifications', snapshot, self.receive, self.failed)

    def receive(self, rows):
        if not self.owner.store.settings.get('notifications_enabled'):
            return
        fresh = self.delta.update(rows, self.owner.store.settings.get('notifications_apps', ''))
        if fresh:
            self.owner.cloud.notify(fresh)
        self.report('Connected. Watching for new Windows notifications.')

    def failed(self, message):
        self.timer.stop()
        self.owner.store.settings['notifications_enabled'] = False
        self.owner.store.save()
        self.access_changed.emit(False)
        self.owner.cloud.clear_notifications()
        self.report(message)
