"""Small per-account RAM outbox, separate from disposable session events."""
import hashlib
import json
import threading
from collections import OrderedDict


def chat_digest(message):
    fields = [message.get(key) for key in ("sender", "recipient", "text", "targets")]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()


class ChatState:
    def __init__(self, username):
        self.username = username
        self.lock = threading.Lock()
        self.outbox = OrderedDict()
        self.received = OrderedDict()  # (sender, message_id) -> content hash only

    def enqueue(self, message):
        if message["sender"] != self.username:
            raise ValueError("Outbox belongs to another account")
        with self.lock:
            if len(self.outbox) >= 500:
                raise ValueError("Outbox is full; reconnect to deliver pending messages")
            self.outbox[message["message_id"]] = {**message, "targets": list(message["targets"]), "status": "PENDING"}

    def pending(self):
        with self.lock:
            return [{**item, "targets": list(item["targets"])} for item in self.outbox.values()]

    def status(self, message_id, status):
        with self.lock:
            item = self.outbox.get(message_id)
            if item is None:
                return False
            if status == "DELIVERED":
                del self.outbox[message_id]
            else:
                item["status"] = status
            return True

    def reset_sending(self):
        with self.lock:
            for item in self.outbox.values():
                item["status"] = "PENDING"

    def already_received(self, message):
        with self.lock:
            previous = self.received.get((message["sender"], message["message_id"]))
        if previous is not None and previous != chat_digest(message):
            raise ValueError("Message ID reused with different content")
        return previous is not None

    def remember(self, message):
        with self.lock:
            self.received[(message["sender"], message["message_id"])] = chat_digest(message)
            while len(self.received) > 5000:
                self.received.popitem(last=False)
