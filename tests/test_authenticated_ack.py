"""Only a matching authenticated ACK from the actual peer advances a send."""
import os
import socket
import threading
import time
import unittest
import uuid

from app.common.protocol import ACK, HEADER, decode_frame, encode_frame
from app.security.crypto import CryptoBox
from app.transport.reliable_udp import ReliableUDP


class AuthenticatedAckTests(unittest.TestCase):
    def test_forged_tampered_wrong_key_and_wrong_peer_acks_are_ignored(self):
        key, captured, ready, errors = os.urandom(32), [], threading.Event(), []
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None,
                             ack_timeout=.03, max_retries=30)
        receiver = ReliableUDP("127.0.0.1", 0, key, lambda *_: None)
        self.addCleanup(sender.close)
        self.addCleanup(receiver.close)
        original = receiver._sendto

        def intercept(raw, peer):
            captured.append((raw, peer))
            ready.set()

        receiver._sendto = intercept

        def transmit():
            try:
                sender.send(("127.0.0.1", receiver.port), {"secret": "synthetic"}, uuid.uuid4())
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=transmit)
        worker.start()
        try:
            self.assertTrue(ready.wait(1))
            raw, peer = captured[0]
            kind, packet, stream, sequence, ciphertext = decode_frame(raw)
            self.assertEqual(kind, ACK)
            credit = receiver.crypto.decrypt(ciphertext, raw[:HEADER.size])
            header = encode_frame(ACK, packet, stream, sequence)
            wrong_key = header + CryptoBox(os.urandom(32)).encrypt(credit, header)
            wrong_sequence = encode_frame(ACK, packet, stream, sequence + 1) + ciphertext
            for invalid in (header, wrong_key, raw[:-1], raw[:-1] + bytes([raw[-1] ^ 1]), wrong_sequence):
                original(invalid, peer)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as attacker:
                attacker.sendto(raw, peer)
            time.sleep(.1)
            self.assertTrue(worker.is_alive(), errors)
            self.assertTrue(all(not value[0].ready.is_set() for value in sender.pending_acks.values()))
            receiver._sendto = original
            original(raw, peer)
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
        finally:
            receiver._sendto = original
            worker.join(2)
