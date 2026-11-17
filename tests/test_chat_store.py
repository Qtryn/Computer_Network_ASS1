"""Persistent per-account identity, duplicate suppression and immutable relay data."""
import tempfile
import unittest
import uuid
from pathlib import Path

from app.features.chat import ChatService
from app.features.chat_store import DurableChatState, RelayChatStore


class ChatStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "chat.sqlite3"
        self.message = ChatService.build_message("alice", "bob", "private fixture",
            message_id=str(uuid.uuid4()), targets=["bob"])

    def test_outbox_survives_reopen_and_is_partitioned_by_account(self):
        alice = DurableChatState("alice", self.path)
        alice.enqueue(self.message)
        alice.status(self.message["message_id"], "SENDING")
        reopened = DurableChatState("alice", self.path)
        reopened.reset_sending()
        self.assertEqual(reopened.pending(), [{**self.message, "status": "PENDING"}])
        self.assertEqual(reopened.contacts(), ["bob"])
        bob = DurableChatState("bob", self.path)
        self.assertEqual(bob.pending(), [])
        self.assertEqual(bob.history(), [])
        with self.assertRaisesRegex(ValueError, "another account"):
            bob.enqueue(self.message)
        reopened.status(self.message["message_id"], "DELIVERED")
        self.assertFalse(reopened.status(self.message["message_id"], "SENDING"))
        self.assertEqual(DurableChatState("alice", self.path).pending(), [])

    def test_inbox_commit_and_dedup_survive_restart(self):
        bob = DurableChatState("bob", self.path)
        self.assertTrue(bob.accept(self.message))
        reopened = DurableChatState("bob", self.path)
        self.assertFalse(reopened.accept(self.message))
        self.assertEqual(reopened.history(), [self.message])
        self.assertEqual(reopened.contacts(), ["alice"])
        with self.assertRaisesRegex(ValueError, "different content"):
            reopened.accept({**self.message, "text": "changed"})
        self.assertEqual(reopened.history(), [self.message])

    def test_relay_retains_only_the_intended_targets_pending_until_their_ack(self):
        relay = RelayChatStore(self.path)
        relay.put(self.message)
        relay.put(self.message)
        self.assertEqual(RelayChatStore(self.path).pending("bob"), [self.message])
        self.assertEqual(relay.pending("charlie"), [])
        key = ("alice", self.message["message_id"])
        self.assertFalse(relay.acknowledge(key, "charlie"))
        self.assertEqual(relay.pending("bob"), [self.message])
        with self.assertRaisesRegex(ValueError, "different content"):
            relay.put({**self.message, "text": "changed"})
        self.assertTrue(relay.acknowledge(key, "bob"))
        self.assertEqual(RelayChatStore(self.path).pending("bob"), [])
        self.assertEqual(relay.delivery(key)["acked"], {"bob"})

    def test_pending_relay_queue_is_bounded_and_existing_retries_remain_valid(self):
        relay = RelayChatStore(self.path, pending_limit=1)
        relay.put(self.message)
        next_message = {**self.message, "message_id": str(uuid.uuid4())}
        with self.assertRaisesRegex(ValueError, "limit"):
            relay.put(next_message)
        relay.put(self.message)
        relay.acknowledge(("alice", self.message["message_id"]), "bob")
        relay.put(next_message)
        self.assertEqual(relay.pending("bob"), [next_message])
