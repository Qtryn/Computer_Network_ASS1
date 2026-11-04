import os
import unittest
import uuid

from cryptography.exceptions import InvalidTag

from app.common.protocol import ACK, DATA, decode_frame, decode_message, encode_frame, encode_message
from app.security.crypto import CryptoBox


class ProtocolTests(unittest.TestCase):
    def test_round_trip_with_raw_file_bytes(self):
        original = {"type": "FILE_CHUNK", "index": 4, "data": b"\x00\xff\x10abc"}
        self.assertEqual(decode_message(encode_message(original)), original)

    def test_frame(self):
        packet_id, stream_id = uuid.uuid4(), uuid.uuid4()
        self.assertEqual(decode_frame(encode_frame(DATA, packet_id, stream_id, 21, b"abc")),
                         (DATA, packet_id, stream_id, 21, b"abc"))
        self.assertEqual(decode_frame(encode_frame(ACK, packet_id, stream_id, 21))[0], ACK)

    def test_aes_gcm_tamper_detected(self):
        crypto = CryptoBox(os.urandom(32))
        plaintext = b"student-network-app"
        encrypted = crypto.encrypt(plaintext, b"packet-header")
        self.assertNotIn(plaintext, encrypted)
        self.assertEqual(crypto.decrypt(encrypted, b"packet-header"), plaintext)
        damaged = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
        with self.assertRaises(InvalidTag):
            crypto.decrypt(damaged, b"packet-header")


if __name__ == "__main__":
    unittest.main()
