"""First-open preferences, saved locally before any optional connection is used."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (QWizard, QWizardPage, QFormLayout, QVBoxLayout, QLabel,
    QLineEdit, QComboBox, QCheckBox, QPushButton, QFileDialog, QColorDialog, QApplication)
from .storage import WIDGETS


class Onboarding(QWizard):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('Welcome to Notch')
        self.setWizardStyle(QWizard.ClassicStyle)
        palette = self.palette()
        for role in (QPalette.Window, QPalette.Base, QPalette.Button, QPalette.AlternateBase):
            palette.setColor(role, QColor('#151518'))
        for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
            palette.setColor(role, QColor('#f4f4f7'))
        self.setPalette(palette)
        self.setStyleSheet('QWizard, QWizardPage { background: #151518; } QLabel { color: #f4f4f7; }')
        self.resize(600, 500)
        self.controls = {}
        s = owner.store.settings
        page, form = self.add_page('First, what should Snippy call you?', 'Your name and preferences stay on this PC. You can change them in Settings.')
        self.name = QLineEdit()
        self.name.setMaxLength(40)
        form.addRow('Your name', self.name)
        page.registerField('name*', self.name)
        self.name.setText(s['user_name'])
        self.add_page('Make yourself at home', 'Choose a display and colour. Drag Snippy freely between your displays.')
        form = self.current_form
        display = QComboBox()
        display.addItems([screen.name() for screen in QApplication.screens()])
        display.setCurrentIndex(min(s['screen'], display.count()-1))
        self.display = display
        form.addRow('Notch display', display)
        self.accent = QLineEdit(s['accent'])
        form.addRow('Accent colour', self.accent)
        colour = QPushButton('Choose colour')
        colour.clicked.connect(self.pick_colour)
        form.addRow('', colour)
        self.check(form, 'animation', 'Animate Snippy and the notch')
        self.check(form, 'hour24', 'Use a 24-hour clock')
        self.add_page('Your desktop, your widgets', 'Select what belongs inside the notch. Desktop tiles can be added in Settings → Desktop.')
        self.widgets = {}
        for name in WIDGETS:
            check = QCheckBox(name)
            check.setChecked(name in s['enabled'])
            self.widgets[name] = check
            self.current_form.addRow(check)
        self.add_page('Weather and your workspace', 'Windows can provide your location with permission. Forecasts come from Open-Meteo; Windows Weather does not provide a supported forecast feed for this app.')
        self.source = QComboBox()
        self.source.addItems(['City', 'Windows location'])
        self.source.setCurrentText(s['weather_source'])
        self.current_form.addRow('Weather location', self.source)
        self.city = QLineEdit(s['city'])
        self.current_form.addRow('City (fallback)', self.city)
        self.check(self.current_form, 'fahrenheit', 'Use Fahrenheit (change on the widget too)')
        self.folder = QLineEdit(s['search_root'])
        self.current_form.addRow('Cowork folder', self.folder)
        pick = QPushButton('Choose folder')
        pick.clicked.connect(self.pick_folder)
        self.current_form.addRow('', pick)
        self.add_page('How would you like to work?', 'Voice is optional. Hold left Ctrl + Alt to speak, then release to send. Offline recognition supports US and Indian English. Windows microphone permission is required.')
        self.check(self.current_form, 'voice_hotkey', 'Enable hold-to-talk (Ctrl + Alt)')
        self.check(self.current_form, 'speak_replies', 'Read typed replies aloud too')
        self.language = QComboBox()
        self.language.addItems(['English (US)', 'English (India)'])
        self.language.setCurrentText(s['speech_language'])
        self.current_form.addRow('Speech accent', self.language)
        self.check(self.current_form, 'live_news', 'Refresh public news every 15 minutes')
        self.check(self.current_form, 'notifications_enabled', 'Announce Windows notifications')
        self.check(self.current_form, 'notifications_preview', 'Include message previews')
        self.add_page('Ready when you are', 'Click Finish to save. Optional accounts are added afterwards in Settings → Connections; Notion is an addable MCP app. Nothing connects automatically.')
        message = QLabel('Snippy sleeps after one idle minute to release AI memory.\n\nClick the cloud for a small typing bar. Only the expand button opens the full chat. Your conversations are saved locally in the chat library.')
        message.setWordWrap(True)
        self.current_form.addRow(message)

    def add_page(self, title, subtitle):
        page = QWizardPage()
        page.setTitle(title)
        page.setSubTitle(subtitle)
        form = QFormLayout(page)
        form.setVerticalSpacing(12)
        self.current_form = form
        self.addPage(page)
        return page, form

    def check(self, form, key, text):
        control = QCheckBox(text)
        control.setChecked(self.owner.store.settings[key])
        self.controls[key] = control
        form.addRow(control)

    def pick_colour(self):
        color = QColorDialog.getColor(QColor(self.accent.text()), self)
        if color.isValid():
            self.accent.setText(color.name())

    def pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose cowork folder', self.folder.text())
        if path:
            self.folder.setText(path)

    def validateCurrentPage(self):
        from PySide6.QtWidgets import QMessageBox
        if self.currentId() == 0 and not self.name.text().strip():
            return False
        if self.currentId() == 1 and not QColor(self.accent.text()).isValid():
            QMessageBox.information(self, 'Colour', 'Choose a valid accent colour.')
            return False
        if self.currentId() == 3 and not Path(self.folder.text()).is_dir():
            QMessageBox.information(self, 'Workspace', 'Choose an existing cowork folder.')
            return False
        return True

    def accept(self):
        s = self.owner.store.settings
        s.update(user_name=self.name.text().strip(), accent=QColor(self.accent.text()).name(),
                 screen=self.display.currentIndex(), city=self.city.text().strip(),
                 search_root=self.folder.text().strip(), weather_source=self.source.currentText(),
                 enabled=[name for name, check in self.widgets.items() if check.isChecked()],
                 speech_language=self.language.currentText(), onboarding_complete=True)
        s.update({key: check.isChecked() for key, check in self.controls.items()})
        self.owner.store.save()
        from .ui import STYLE
        QApplication.instance().setStyleSheet(STYLE.replace('#b7b0ff', s['accent']))
        self.owner.rebuild()
        self.owner.cloud.sync_preferences()
        self.owner.cloud.show_input(True)
        self.owner.cloud.refresh_size()
        self.owner.cloud.follow()
        self.owner.notifications.configure()
        super().accept()

