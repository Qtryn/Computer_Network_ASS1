"""Every message the app can produce must fit in ONE UDP datagram (MAX_DATAGRAM).

Wire size = 42-byte frame header + 28-byte AES-GCM overhead + 2-byte metadata
length + JSON metadata + raw data. If this is exceeded, ReliableUDP raises
"UDP datagram too large" and the message is never sent.

Run: python -m unittest discover -s tests -p "test_packet_budget*" -v
"""
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from app.common.config import FILE_CHUNK_SIZE, MAX_CHAT_BYTES, MAX_DATAGRAM, MAX_FILE_NAME
from app.common.protocol import DATA, HEADER, encode_frame, encode_message
from app.features.chat import ChatService
from app.features.files import FileSender
from app.security.crypto import OVERHEAD, CryptoBox

TOKEN = "f" * 48          # secrets.token_hex(24)
USER = "u" * 20           # longest allowed username
CRYPTO = CryptoBox(os.urandom(32))


def wire_size(message):
    """Bytes on the wire, built exactly like ReliableUDP.send_many does."""
    header = encode_frame(DATA, uuid.uuid4(), uuid.uuid4(), 0xFFFFFFFF)
    return len((header + CRYPTO.encrypt(encode_message(message), header)))


class FilePacketBudgetTests(unittest.TestCase):
    def test_fixed_overheads(self):
        self.assertEqual(HEADER.size, 42)
        self.assertEqual(OVERHEAD, 28)

    def test_full_chunk_with_worst_case_metadata_fits(self):
        message = {"file_id": str(uuid.uuid4()), "sender": USER, "recipient": USER,
                   "type": "FILE_CHUNK", "index": 99_999_999, "token": TOKEN,
                   "data": b"\x00" * FILE_CHUNK_SIZE}
        size = wire_size(message)
        print(f"\n[budget] full FILE_CHUNK = {size} B, headroom {MAX_DATAGRAM - size} B")
        self.assertLessEqual(size, MAX_DATAGRAM)

    def test_file_start_with_longest_multibyte_name_fits(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "a.bin"
            source.write_bytes(b"x" * 10)
            _, _, packets = FileSender().prepare(source, USER, USER, display_name="ệ" * MAX_FILE_NAME)
            start = {**next(packets), "token": TOKEN}
            packets.close()
        size = wire_size(start)
        print(f"[budget] worst-case FILE_START = {size} B, headroom {MAX_DATAGRAM - size} B")
        self.assertLessEqual(size, MAX_DATAGRAM)

    def test_real_packets_of_a_file_all_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "data.bin"
            source.write_bytes(os.urandom(FILE_CHUNK_SIZE * 5 + 123))
            _, _, packets = FileSender().prepare(source, USER, USER)
            for packet in packets:
                self.assertLessEqual(wire_size({**packet, "token": TOKEN}), MAX_DATAGRAM, packet["type"])


class ChatPacketBudgetTests(unittest.TestCase):
    """Property: any chat text that ChatService ACCEPTS must be sendable.

    JSON escapes some characters (" -> \\", control chars -> \\u00XX), so a text
    below MAX_CHAT_BYTES can still produce a metadata block larger than the limit.
    """
    TEXTS = {
        "ascii": "x" * MAX_CHAT_BYTES,
        "vietnamese": "ệ" * (MAX_CHAT_BYTES // 3),
        "quotes": '"' * MAX_CHAT_BYTES,
        "backslashes": "\\" * MAX_CHAT_BYTES,
        "control chars": "\x01" * MAX_CHAT_BYTES,
    }

    def test_accepted_chat_text_always_fits_one_datagram(self):
        for label, text in self.TEXTS.items():
            with self.subTest(label):
                try:
                    event = ChatService.build_message(USER, USER, text)
                except ValueError:
                    continue  # rejected up front is fine
                size = wire_size({**event, "token": TOKEN})
                self.assertLessEqual(size, MAX_DATAGRAM,
                                     f"accepted {label} text needs {size} B > {MAX_DATAGRAM}")

    def test_escaped_text_at_datagram_boundary(self):
        empty = {"type": "CHAT", "sender": USER, "recipient": USER, "text": "", "token": TOKEN}
        budget = MAX_DATAGRAM - wire_size(empty)
        for character, encoded_size in [('"', 2), ("\\", 2), ("\x00", 6)]:
            with self.subTest(character=repr(character)):
                count, remainder = divmod(budget, encoded_size)
                text = character * count + "x" * remainder
                event = ChatService.build_message(USER, USER, text)
                self.assertEqual(wire_size({**event, "token": TOKEN}), MAX_DATAGRAM)
                with self.assertRaises(ValueError):
                    ChatService.build_message(USER, USER, text + "x")


if __name__ == "__main__":
    unittest.main()