"""SQLite chat queues, inboxes and relay acknowledgements."""
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.features.outbox import ChatState, chat_digest


class ChatDatabase:
    def __init__(self, path, schema):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript(schema)

    @contextmanager
    def transaction(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            yield db


class DurableChatState(ChatState):
    """One local profile. Data is partitioned by authenticated account."""

    def __init__(self, username, path):
        super().__init__(username)
        self.database = ChatDatabase(path, """
            CREATE TABLE IF NOT EXISTS local_chat (
                seq INTEGER PRIMARY KEY,
                owner TEXT NOT NULL, sender TEXT NOT NULL, id TEXT NOT NULL,
                body TEXT NOT NULL, digest TEXT NOT NULL, status TEXT,
                UNIQUE(owner, sender, id)
            );
            CREATE INDEX IF NOT EXISTS local_outbox ON local_chat(owner, status, seq);
        """)

    def enqueue(self, message):
        if message["sender"] != self.username:
            raise ValueError("Outbox belongs to another account")
        with self.database.transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            count, = db.execute(
                "SELECT COUNT(*) FROM local_chat WHERE owner=? AND status IN ('PENDING', 'SENDING')",
                (self.username,)).fetchone()
            if count >= 500:
                raise ValueError("Outbox is full; reconnect to deliver pending messages")
            db.execute("INSERT INTO local_chat(owner,sender,id,body,digest,status) VALUES (?,?,?,?,?,?)",
                       (self.username, self.username, message["message_id"],
                        json.dumps(message), chat_digest(message), "PENDING"))

    def pending(self):
        with self.database.transaction() as db:
            return [{**json.loads(body), "status": status} for body, status in db.execute(
                "SELECT body,status FROM local_chat WHERE owner=? AND status IN ('PENDING','SENDING') ORDER BY seq",
                (self.username,))]

    def status(self, message_id, status):
        with self.database.transaction() as db:
            return bool(db.execute(
                "UPDATE local_chat SET status=? WHERE owner=? AND sender=? AND id=? AND status IN ('PENDING','SENDING')",
                (status, self.username, self.username, message_id)).rowcount)

    def reset_sending(self):
        with self.database.transaction() as db:
            db.execute("UPDATE local_chat SET status='PENDING' WHERE owner=? AND status='SENDING'",
                       (self.username,))

    def accept(self, message):
        """Commit before acknowledging. An identical retry is safe across restarts."""
        with self.database.transaction() as db:
            digest = chat_digest(message)
            key = (self.username, message["sender"], message["message_id"])
            inserted = db.execute(
                "INSERT OR IGNORE INTO local_chat(owner,sender,id,body,digest) VALUES (?,?,?,?,?)",
                (*key, json.dumps(message), digest)).rowcount
            old, = db.execute("SELECT digest FROM local_chat WHERE owner=? AND sender=? AND id=?",
                              key).fetchone()
            if old != digest:
                raise ValueError("Message ID reused with different content")
            return bool(inserted)

    def history(self):
        with self.database.transaction() as db:
            rows = db.execute(
                "SELECT body,status FROM local_chat WHERE owner=? ORDER BY seq DESC LIMIT 500",
                (self.username,)).fetchall()
        return [{**json.loads(body), **({"outgoing": True, "delivery": status} if status else {})}
                for body, status in reversed(rows)]

    def contacts(self):
        messages = self.history() + self.pending()
        return sorted({name for item in messages for name in [item["sender"], *item["targets"]]
                       if name != self.username})


class RelayChatStore:
    """Immutable messages and a separate acknowledgement per destination."""

    def __init__(self, path, pending_limit=500):
        if pending_limit < 1:
            raise ValueError("Pending relay limit must be positive")
        self.pending_limit = pending_limit
        self.database = ChatDatabase(path, """
            CREATE TABLE IF NOT EXISTS relay_chat (
                seq INTEGER PRIMARY KEY,
                sender TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                digest TEXT NOT NULL, UNIQUE(sender, id)
            );
            CREATE TABLE IF NOT EXISTS relay_target (
                seq INTEGER NOT NULL REFERENCES relay_chat(seq),
                username TEXT NOT NULL, acked INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(seq, username)
            );
            CREATE INDEX IF NOT EXISTS relay_pending ON relay_target(username, acked, seq);
            CREATE TABLE IF NOT EXISTS channel_member (
                channel TEXT NOT NULL, username TEXT NOT NULL, PRIMARY KEY(channel, username)
            );
        """)

    def put(self, message):
        key = (message["sender"], message["message_id"])
        digest = chat_digest(message)
        with self.database.transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM relay_chat WHERE sender=? AND id=?", key).fetchone():
                count, = db.execute("""
                    SELECT COUNT(*) FROM relay_chat WHERE sender=? AND EXISTS (
                        SELECT 1 FROM relay_target WHERE relay_target.seq=relay_chat.seq AND acked=0
                    )
                """, (message["sender"],)).fetchone()
                if count >= self.pending_limit:
                    raise ValueError("Server pending chat limit reached")
            db.execute("INSERT OR IGNORE INTO relay_chat(sender,id,body,digest) VALUES (?,?,?,?)",
                       (*key, json.dumps(message), digest))
            seq, old = db.execute("SELECT seq,digest FROM relay_chat WHERE sender=? AND id=?",
                                  key).fetchone()
            if old != digest:
                raise ValueError("Message ID reused with different content")
            db.executemany("INSERT OR IGNORE INTO relay_target(seq,username) VALUES (?,?)",
                           [(seq, username) for username in message["targets"]])

    def acknowledge(self, key, username):
        with self.database.transaction() as db:
            return bool(db.execute("""
                UPDATE relay_target SET acked=1 WHERE username=? AND seq=(
                    SELECT seq FROM relay_chat WHERE sender=? AND id=?
                )
            """, (username, *key)).rowcount)

    def delivery(self, key):
        with self.database.transaction() as db:
            rows = db.execute("""
                SELECT username,acked FROM relay_target JOIN relay_chat USING(seq)
                WHERE sender=? AND id=? ORDER BY username
            """, key).fetchall()
        if rows:
            return {"targets": [name for name, _ in rows],
                    "acked": {name for name, acked in rows if acked}}
        return None

    def pending(self, username, limit=4):
        with self.database.transaction() as db:
            return [json.loads(body) for body, in db.execute("""
                SELECT body FROM relay_target JOIN relay_chat USING(seq)
                WHERE username=? AND acked=0 ORDER BY seq LIMIT ?
            """, (username, limit))]

    def join_channel(self, channel, username):
        with self.database.transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM channel_member WHERE channel=? AND username=?",
                          (channel, username)).fetchone():
                return
            if db.execute("SELECT COUNT(*) FROM channel_member WHERE username=?", (username,)).fetchone()[0] >= 8:
                raise ValueError("Each account may join up to 8 channels")
            if db.execute("SELECT COUNT(*) FROM channel_member WHERE channel=?", (channel,)).fetchone()[0] >= 64:
                raise ValueError("Channel is full")
            db.execute("INSERT OR IGNORE INTO channel_member(channel,username) VALUES (?,?)",
                       (channel, username))

    def channels(self, username):
        with self.database.transaction() as db:
            rows = db.execute("""
                SELECT channel, username FROM channel_member WHERE channel IN (
                    SELECT channel FROM channel_member WHERE username=?
                ) ORDER BY channel, username
            """, (username,)).fetchall()
        channels = {}
        for channel, member in rows:
            channels.setdefault(channel, []).append(member)
        return channels
