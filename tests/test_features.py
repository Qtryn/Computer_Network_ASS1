"""Run: python -m unittest discover -s tests -v"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from app.features.chat import ChatService
from app.features.files import FileReceiver, FileSender, safe_filename, sha256_file


class ChatTests(unittest.TestCase):
    def test_broadcast_and_private_routing(self):
        self.assertEqual(ChatService.recipients("alice", "*", ["alice", "bob", "cindy"]),
                         ["bob", "cindy"])
        self.assertEqual(ChatService.recipients("alice", "bob", ["alice", "bob"]), ["bob"])
        with self.assertRaises(ValueError):
            ChatService.recipients("alice", "absent", ["alice", "bob"])

    def test_chat_validation(self):
        with self.assertRaises(ValueError):
            ChatService.build_message("alice", "bob", " ")
        with self.assertRaises(ValueError):
            ChatService.build_message("alice", "bob", "x" * 1000)


class FileTests(unittest.TestCase):
    def _transfer(self, file_bytes):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            original = folder / "input.dat"
            original.write_bytes(file_bytes)
            transfer_id, total, packets = FileSender().prepare(original, "alice", "bob")
            receiver = FileReceiver(folder / "received")
            messages = list(packets)
            self.assertEqual(total, len(messages))
            self.assertEqual(messages[0]["file_id"], transfer_id)
            results = [receiver.process(packet) for packet in messages]
            self.assertEqual(results[-1]["type"], "FILE_COMPLETE")
            received = Path(results[-1]["path"])
            self.assertEqual(received.read_bytes(), file_bytes)
            self.assertEqual(sha256_file(received), hashlib.sha256(file_bytes).hexdigest())
            receiver.close()

    def test_binary_file_many_chunks(self):
        self._transfer(bytes(range(256)) * 40)

    def test_empty_file(self):
        self._transfer(b"")

    def test_custom_chunk_size(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.bin"
            source.write_bytes(b"1234567890" * 37)
            _, _, messages = FileSender(chunk_size=64).prepare(source, "alice", "bob")
            receiver = FileReceiver(Path(directory) / "received")
            try:
                for message in messages:
                    result = receiver.process(message)
                self.assertEqual(result["type"], "FILE_COMPLETE")
                self.assertEqual(Path(result["path"]).read_bytes(), source.read_bytes())
            finally:
                receiver.close()

    def test_utf8_content(self):
        self._transfer("Xin chào. UTF-8 tiếng Việt.".encode("utf-8") * 60)

    def test_corrupt_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "test.dat"
            path.write_bytes(b"A" * 900)
            _, _, packets = FileSender().prepare(path, "alice", "bob")
            messages = list(packets)
            messages[1] = {**messages[1], "data": b"B" + messages[1]["data"][1:]}
            receiver = FileReceiver(folder / "received")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                for message in messages:
                    receiver.process(message)
            self.assertEqual(list((folder / "received").iterdir()), [])

    def test_filename_safety(self):
        self.assertEqual(safe_filename("../../documents/file.txt"), "file.txt")
        self.assertEqual(safe_filename(r"C:\users\alice\report.docx"), "report.docx")
        self.assertEqual(safe_filename("CON.txt"), "_CON.txt")


if __name__ == "__main__":
    unittest.main()
