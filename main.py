import ctypes
import logging
import sys

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication
from nook.storage import DATA, Store
from nook.ui import Notch, STYLE


def main():
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Nook.Windows')
    app = QApplication(sys.argv)
    app.setApplicationName('Nook')
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
    notch = Notch(Store())
    notch.show()
    if '--settings' in sys.argv:
        QTimer.singleShot(300, notch.open_settings)
    result = app.exec()
    notch.search_cancel.set()
    lock.unlock()
    return result


if __name__ == '__main__':
    sys.exit(main())
