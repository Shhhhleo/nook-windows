"""Add optional apps; no Notion account is assumed or connected by default."""
import json
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QPushButton, QListWidget, QLabel, QMessageBox, QPlainTextEdit)
from . import mcp_client


class ConnectionsDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('Apps connected through MCP')
        self.resize(650, 650)
        layout = QVBoxLayout(self)
        self.apps = QListWidget()
        self.apps.setMaximumHeight(100)
        self.apps.currentRowChanged.connect(self.selected)
        layout.addWidget(self.apps)
        form = QFormLayout()
        self.preset = QComboBox()
        self.preset.addItems(['Custom app', 'Notion'])
        self.preset.currentTextChanged.connect(self.preset_changed)
        form.addRow('Add an app', self.preset)
        self.name = QLineEdit()
        self.url = QLineEdit()
        self.url.setPlaceholderText('https://example.com/mcp')
        self.auth = QComboBox()
        self.auth.addItems(['OAuth', 'Bearer token', 'None (local server)'])
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        form.addRow('Name', self.name)
        form.addRow('MCP URL', self.url)
        form.addRow('Sign-in', self.auth)
        form.addRow('Token (if required)', self.token)
        layout.addLayout(form)
        row = QHBoxLayout()
        for text, action in [('Add app', self.add), ('Connect / refresh tools', self.connect_app), ('Remove', self.remove)]:
            button = QPushButton(text)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)
        self.tools = QComboBox()
        self.tools.currentIndexChanged.connect(self.select_tool)
        layout.addWidget(self.tools)
        self.arguments = QPlainTextEdit('{}')
        self.arguments.setMaximumHeight(120)
        self.arguments.setPlaceholderText('Tool arguments as JSON')
        layout.addWidget(self.arguments)
        run = QPushButton('Review and run tool')
        run.clicked.connect(self.run_tool)
        layout.addWidget(run)
        self.status = QLabel('Add only apps you trust. Connecting opens the provider’s sign-in. Each tool call is reviewed before it runs.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        self.reload()

    def reload(self):
        self.apps.clear()
        for app in self.owner.store.settings['mcp_connections']:
            self.apps.addItem(app['name'])
        if self.apps.count():
            self.apps.setCurrentRow(0)

    def current(self):
        rows = self.owner.store.settings['mcp_connections']
        index = self.apps.currentRow()
        return rows[index] if 0 <= index < len(rows) else None

    def selected(self, _):
        self.tools.clear()
        app = self.current()
        if app:
            for tool in app.get('tools', []):
                self.tools.addItem(tool['name'], tool)

    def preset_changed(self, name):
        if name == 'Notion':
            self.name.setText('Notion')
            self.url.setText('https://mcp.notion.com/mcp')
            self.auth.setCurrentText('OAuth')

    def add(self):
        try:
            url = mcp_client.validate_url(self.url.text().strip())
            if not self.name.text().strip():
                raise ValueError('Give this app a name.')
            identity = uuid.uuid4().hex
            self.owner.store.settings['mcp_connections'].append(dict(id=identity, name=self.name.text().strip()[:60],
                url=url, auth=self.auth.currentText(), tools=[]))
            if self.token.text():
                self.owner.store.secret('mcp:' + identity + ':bearer', self.token.text().strip())
            self.owner.store.save()
            self.token.clear()
            self.reload()
            self.apps.setCurrentRow(self.apps.count()-1)
        except ValueError as error:
            self.status.setText(str(error))

    def connect_app(self):
        app = self.current()
        if app:
            self.status.setText('Connecting… complete sign-in in your browser if prompted.')
            def done(tools):
                if app not in self.owner.store.settings['mcp_connections']:
                    return
                app['tools'] = tools
                self.owner.store.save()
                self.selected(0)
                self.status.setText('%s tools available. Snippy can propose using them in chat.' % len(tools))
            self.owner.run_job('mcp-connect', lambda: mcp_client.invoke(self.owner.store, app['id'], connect=True), done, self.status.setText)

    def remove(self):
        app = self.current()
        if app:
            self.owner.store.settings['mcp_connections'].remove(app)
            for suffix in ('tokens', 'client', 'bearer'):
                self.owner.store.secret('mcp:' + app['id'] + ':' + suffix, '')
            self.owner.store.save()
            self.reload()

    def select_tool(self, _):
        tool = self.tools.currentData()
        if tool:
            self.output.setPlainText(tool.get('description', '') + '\n\n' + json.dumps(tool.get('inputSchema', {}), indent=2))
            self.arguments.setPlainText('{}')

    def run_tool(self):
        app, tool = self.current(), self.tools.currentData()
        if not app or not tool:
            return
        try:
            arguments = json.loads(self.arguments.toPlainText())
            if not isinstance(arguments, dict):
                raise ValueError('Arguments must be a JSON object.')
            import jsonschema
            jsonschema.validate(arguments, tool['inputSchema'])
        except Exception as error:
            self.status.setText(str(error)[:500])
            return
        if QMessageBox.question(self, 'Run app tool', app['name'] + ' · ' + tool['name'] + '\n\n' + json.dumps(arguments, indent=2)[:6000]) != QMessageBox.Yes:
            return
        self.status.setText('Working…')
        def done(result):
            self.output.setPlainText(result['text'])
            self.status.setText('App reported an error.' if result.get('error') else 'Done.')
        self.owner.run_job('mcp-tool', lambda: mcp_client.invoke(self.owner.store, app['id'], tool['name'], arguments), done, self.status.setText)
