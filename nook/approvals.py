"""A single queue of actions waiting for the user's yes or no.

Worker threads call ask() and block until the user answers in the UI.
Background services (WhatsApp drafts) call post() with a callback instead.
"""
import itertools
import threading

from PySide6.QtCore import QObject, Signal, Slot


class Approvals(QObject):
    changed = Signal()
    _deliver = Signal(object)

    def __init__(self):
        super().__init__()
        self.pending = []
        self.ids = itertools.count(1)
        self.lock = threading.Lock()
        self._deliver.connect(self._add)

    @Slot(object)
    def _add(self, request):
        with self.lock:
            if request['event'].is_set():
                return  # Timed out before the UI received it.
            self.pending.append(request)
        self.changed.emit()

    def current(self):
        return self.pending[0] if self.pending else None

    def ask(self, kind, title, detail, timeout=900):
        """Blocking request from a worker thread.

        Returns (approved, detail). detail may have been edited by the user.
        Silence counts as no.
        """
        request = {'id': next(self.ids), 'kind': kind, 'title': title, 'detail': detail,
                   'event': threading.Event(), 'approved': False, 'callback': None}
        self._deliver.emit(request)
        if not request['event'].wait(timeout):
            self.answer(request, False)
            return False, detail
        return request['approved'], request['detail']

    def post(self, kind, title, detail, callback, edit=None):
        """Non-blocking request. callback(approved, text) runs on the UI thread."""
        request = {'id': next(self.ids), 'kind': kind, 'title': title, 'detail': detail,
                   'event': threading.Event(), 'approved': False, 'callback': callback, 'edit': edit}
        self._deliver.emit(request)
        return request

    def answer(self, request, approved, text=None):
        with self.lock:
            if request['event'].is_set():
                return
            if request in self.pending:
                self.pending.remove(request)
        request['approved'] = bool(approved)
        if text is not None:
            request['detail'] = text
        request['event'].set()
        if request.get('callback'):
            request['callback'](request['approved'], request['detail'])
        self.changed.emit()
