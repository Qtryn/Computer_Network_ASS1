"""Client-side event handling tests."""

import threading
import unittest
from collections import deque

from app.client import CollaborationClient


class ClientEventTests(unittest.TestCase):
    def make_client(self):
        client = CollaborationClient.__new__(CollaborationClient)
        client.username = "bob"
        client.server_udp = ("127.0.0.1", 9101)
        client.event_lock = threading.Lock()
        client.event_id = 0
        client.events = deque(maxlen=500)
        return client

    def test_server_echo_of_own_chat_is_ignored(self):
        client = self.make_client()
        client._on_udp_message(client.server_udp, None, {
            "type": "CHAT", "sender": "bob", "recipient": "*", "text": "hello",
        })
        self.assertEqual(list(client.events), [])

    def test_chat_from_another_user_is_kept(self):
        client = self.make_client()
        client._on_udp_message(client.server_udp, None, {
            "type": "CHAT", "sender": "alice", "recipient": "bob", "text": "hello",
        })
        self.assertEqual(len(client.events), 1)
        self.assertEqual(client.events[0]["sender"], "alice")
        self.assertEqual(client.events[0]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
