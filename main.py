import ctypes
import logging
import sys

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication
from nook.storage import DATA, Store
from nook.ui import Notch, STYLE


def main():
    length = ctypes.c_uint32()
    if ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) == 15700:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Nook.Windows')
    app = QApplication(sys.argv)
    app.setApplicationName('Notch')
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    lock = QLockFile(str(DATA / 'nook.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        return 0
    logging.basicConfig(filename=str(DATA / 'errors.log'), level=logging.ERROR)
    def report(kind, value, trace):
        logging.error('Unhandled error', exc_info=(kind, value, trace))
    sys.excepthook = report
    store = Store()
    app.setStyleSheet(STYLE.replace('#b7b0ff', store.settings['accent']))
    notch = Notch(store)
    notch.show()
    from nook.news import start_monitor
    start_monitor(notch)
    if not notch.store.settings.get('onboarding_complete'):
        QTimer.singleShot(300, notch.cloud.onboard)
    elif '--settings' in sys.argv:
        QTimer.singleShot(300, notch.open_settings)
    result = app.exec()
    notch.cloud.voice.close()
    notch.search_cancel.set()
    lock.unlock()
    return result


if __name__ == '__main__':
    sys.exit(main())
