"""Choose which WhatsApp chats Snippy manages, and how."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QFormLayout,
                               QLineEdit, QComboBox, QPlainTextEdit, QPushButton, QLabel, QDialogButtonBox)

MODES = [('Draft: ask me before each reply', 'draft'), ('Auto: reply on my behalf', 'auto')]


class ContactsDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.contacts = [dict(c) for c in store.settings.get('whatsapp_contacts', [])]
        self.setWindowTitle('Chats Snippy manages')
        self.resize(760, 480)
        root = QVBoxLayout(self)
        intro = QLabel('Use the chat name exactly as it appears in WhatsApp, or add a phone number with country code '
                       '(for example +91 98765 43210). Instructions tell Snippy how to talk to this person.')
        intro.setWordWrap(True)
        root.addWidget(intro)
        body = QHBoxLayout()
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.load)
        left.addWidget(self.list, 1)
        row = QHBoxLayout()
        add = QPushButton('Add person')
        add.clicked.connect(self.add)
        row.addWidget(add)
        remove = QPushButton('Remove')
        remove.clicked.connect(self.remove)
        row.addWidget(remove)
        left.addLayout(row)
        body.addLayout(left, 2)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText('Mum, Rahul, Team chat…')
        self.name.textEdited.connect(self.store_current)
        form.addRow('Chat name', self.name)
        self.phone = QLineEdit()
        self.phone.setPlaceholderText('Optional, with country code')
        self.phone.textEdited.connect(self.store_current)
        form.addRow('Phone', self.phone)
        self.mode = QComboBox()
        for title, value in MODES:
            self.mode.addItem(title, value)
        self.mode.currentIndexChanged.connect(self.store_current)
        form.addRow('Snippy should', self.mode)
        self.instructions = QPlainTextEdit()
        self.instructions.setPlaceholderText('e.g. Keep it friendly and short. If they ask when I’m free, say I’ll confirm tonight. Never agree to payments.')
        self.instructions.textChanged.connect(self.store_current)
        form.addRow('Instructions', self.instructions)
        body.addLayout(form, 3)
        root.addLayout(body, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.loading = False
        self.refresh()

    def refresh(self, select=0):
        self.list.blockSignals(True)
        self.list.clear()
        for contact in self.contacts:
            self.list.addItem(QListWidgetItem('%s · %s' % (contact.get('name') or 'New person', contact.get('mode', 'draft'))))
        self.list.blockSignals(False)
        if self.contacts:
            self.list.setCurrentRow(min(select, len(self.contacts) - 1))
            self.load(self.list.currentRow())
        else:
            self.load(-1)

    def load(self, index):
        self.loading = True
        contact = self.contacts[index] if 0 <= index < len(self.contacts) else None
        for widget in (self.name, self.phone, self.mode, self.instructions):
            widget.setEnabled(contact is not None)
        contact = contact or {}
        self.name.setText(contact.get('name', ''))
        self.phone.setText(contact.get('phone', ''))
        self.mode.setCurrentIndex(max(0, self.mode.findData(contact.get('mode', 'draft'))))
        self.instructions.setPlainText(contact.get('instructions', ''))
        self.loading = False

    def store_current(self, *_):
        index = self.list.currentRow()
        if self.loading or not 0 <= index < len(self.contacts):
            return
        self.contacts[index].update(name=self.name.text().strip()[:80], phone=self.phone.text().strip()[:30],
                                    mode=self.mode.currentData(), instructions=self.instructions.toPlainText().strip()[:1500])
        self.list.item(index).setText('%s · %s' % (self.contacts[index]['name'] or 'New person', self.contacts[index]['mode']))

    def add(self):
        self.contacts.append({'name': '', 'phone': '', 'mode': 'draft', 'instructions': ''})
        self.refresh(len(self.contacts) - 1)
        self.name.setFocus()

    def remove(self):
        index = self.list.currentRow()
        if 0 <= index < len(self.contacts):
            del self.contacts[index]
            self.refresh(max(0, index - 1))

    def save(self):
        self.store.settings['whatsapp_contacts'] = [c for c in self.contacts if c.get('name') or c.get('phone')]
        for contact in self.store.settings['whatsapp_contacts']:
            contact['name'] = contact.get('name') or contact.get('phone')
        self.store.save()
        self.accept()
