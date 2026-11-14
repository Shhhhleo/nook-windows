"""Small, local chat archive. No network or model process required."""
import json
import uuid
import sqlite3
from contextlib import closing
from datetime import datetime
from . import storage


class Conversations:
    def __init__(self):
        self.path = storage.DATA / 'chats.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT, updated TEXT, messages TEXT)')

    @property
    def chats(self):
        # The library loads titles only. Old transcript bodies do not occupy RAM.
        with closing(sqlite3.connect(self.path)) as db, db:
            return [dict(id=row[0], title=row[1], updated=row[2]) for row in db.execute('SELECT id,title,updated FROM chats ORDER BY updated DESC, rowid DESC')]

    def load(self, identity):
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute('SELECT messages FROM chats WHERE id=?', (identity,)).fetchone()
            return json.loads(row[0]) if row else []

    def save(self, identity, messages):
        if not messages:
            return identity
        identity = identity or uuid.uuid4().hex
        title = next((r['content'] for r in messages if r['role'] == 'user'), 'Conversation')[:70]
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO chats VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,messages=excluded.messages',
                       (identity, title, datetime.now().isoformat(), json.dumps(messages[-200:], ensure_ascii=False)))
        return identity

    def delete(self, identity):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('DELETE FROM chats WHERE id=?', (identity,))
