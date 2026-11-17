"""Direct delivery requires the current TLS-issued pair capability and endpoint."""
import os
import threading
import unittest
import uuid
from collections import deque
from unittest.mock import Mock

from app.client import CollaborationClient
from app.features.chat import ChatService
from app.features.outbox import ChatState
from app.security.peer import peer_stream, signed


class PeerSecurityTests(unittest.TestCase):
    def test_wrong_endpoint_key_old_session_and_tampering_cannot_inject_chat(self):
        client = CollaborationClient.__new__(CollaborationClient)
        client.username = "bob"
        client.server_udp = ("127.0.0.1", 9101)
        client.running = threading.Event()
        client.running.set()
        client.token = "synthetic-session"
        client.event_lock = threading.Lock()
        client.event_id = 0
        client.events = deque(maxlen=500)
        client.chat_state = ChatState("bob")
        client.udp = Mock()
        peer, key, old_key = ("127.0.0.1", 55555), os.urandom(32), os.urandom(32)
        client.peer_routes = {"alice": (peer, key)}
        chat = ChatService.build_message("alice", "bob", "fixture chat",
            message_id=str(uuid.uuid4()), targets=["bob"])
        body = {"type": "DIRECT_CHAT", "sender": "alice", "target": "bob", "chat": chat}
        message = signed(body, key)
        stream = peer_stream(key, "alice", "DIRECT_CHAT")
        invalid = [
            (peer, stream, body),
            (peer, stream, {**message, "chat": {**chat, "text": "modified"}}),
            (peer, stream, signed(body, old_key)),
            (peer, peer_stream(old_key, "alice", "DIRECT_CHAT"), signed(body, old_key)),
            (("127.0.0.1", 55556), stream, message),
        ]
        for args in invalid:
            client._on_udp_message(*args)
        self.assertEqual(list(client.events), [])
        client.udp.send.assert_not_called()
        client._on_udp_message(peer, stream, message)
        client._on_udp_message(peer, stream, message)
        self.assertEqual(len(client.events), 1)
        self.assertEqual(client.events[0]["message_id"], chat["message_id"])
        self.assertEqual(client.udp.send.call_count, 2)  # acknowledge retries without redisplay
        with self.assertRaisesRegex(ValueError, "different content"):
            client._on_udp_message(peer, stream, signed({**body, "chat": {**chat, "text": "changed"}}, key))
