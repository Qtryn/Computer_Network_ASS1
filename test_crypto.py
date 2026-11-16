"""Run: python -m unittest discover -s tests -v"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.exceptions import InvalidTag

from app.security import crypto
from app.security.crypto import (CONTROL_C2S, CONTROL_S2C, KEY_ENV_VAR, NONCE_SIZE, OVERHEAD,
                                 CryptoBox, DecryptError, load_key, max_plaintext_size,
                                 open_control, seal_control)


class CryptoBoxTests(unittest.TestCase):
    def setUp(self):
        self.box = CryptoBox(os.urandom(32))

    def test_round_trip_sizes(self):
        for size in (0, 1, 15, 16, 17, 1024, 65000):
            data = os.urandom(size)
            self.assertEqual(self.box.decrypt(self.box.encrypt(data)), data)

    def test_round_trip_with_aad_and_unicode(self):
        text = "Xin chào, mạng máy tính!".encode("utf-8")
        blob = self.box.encrypt(text, b"header")
        self.assertEqual(self.box.decrypt(blob, b"header"), text)

    def test_overhead_is_28_bytes(self):
        self.assertEqual(OVERHEAD, 28)
        for size in (0, 10, 500):
            self.assertEqual(len(self.box.encrypt(b"x" * size)), size + OVERHEAD)
        self.assertEqual(max_plaintext_size(1200), 1172)
        self.assertEqual(max_plaintext_size(10), 0)

    def test_nonce_never_repeats(self):
        nonces = {self.box.encrypt(b"x")[:NONCE_SIZE] for _ in range(20000)}
        self.assertEqual(len(nonces), 20000)

    def test_same_plaintext_gives_different_ciphertext(self):
        self.assertNotEqual(self.box.encrypt(b"same"), self.box.encrypt(b"same"))

    def test_wrong_key_rejected(self):
        blob = self.box.encrypt(b"secret")
        with self.assertRaises(DecryptError):
            CryptoBox(os.urandom(32)).decrypt(blob)

    def test_every_single_byte_flip_detected(self):
        blob = self.box.encrypt(b"hello world", b"hdr")
        for i in range(len(blob)):
            bad = bytearray(blob)
            bad[i] ^= 0x80
            with self.assertRaises(DecryptError, msg=f"byte {i}"):
                self.box.decrypt(bytes(bad), b"hdr")

    def test_header_aad_is_authenticated(self):
        blob = self.box.encrypt(b"msg", b"seq=1")
        with self.assertRaises(DecryptError):
            self.box.decrypt(blob, b"seq=2")
        with self.assertRaises(DecryptError):
            self.box.decrypt(blob)

    def test_truncated_and_garbage_rejected(self):
        blob = self.box.encrypt(b"abcdef")
        for cut in (0, 5, OVERHEAD - 1):
            with self.assertRaises(DecryptError):
                self.box.decrypt(blob[:cut])
        with self.assertRaises(DecryptError):
            self.box.decrypt(blob[:-1])
        with self.assertRaises(DecryptError):
            self.box.decrypt(os.urandom(64))

    def test_error_is_compatible_with_old_callers(self):
        blob = self.box.encrypt(b"x")
        with self.assertRaises(InvalidTag):
            self.box.decrypt(blob[:-1] + bytes([blob[-1] ^ 1]))
        with self.assertRaises(ValueError):
            self.box.decrypt(b"short")

    def test_invalid_key_length(self):
        for bad in (b"", b"short", b"x" * 16, b"x" * 33, "x" * 32):
            with self.assertRaises(ValueError):
                CryptoBox(bad)


class ControlChannelTests(unittest.TestCase):
    """TCP login channel: base64(AES-GCM(JSON)), one line per message."""

    def setUp(self):
        self.box = CryptoBox(os.urandom(32))
        self.login = {"type": "LOGIN_OK", "token": "ab" * 24, "users": ["alice", "bob"], "udp_port": 9101}

    def test_round_trip(self):
        line = seal_control(self.box, self.login, CONTROL_S2C)
        self.assertEqual(open_control(self.box, line, CONTROL_S2C), self.login)
        self.assertEqual(open_control(self.box, line + b"\n", CONTROL_S2C), self.login)
        self.assertEqual(open_control(self.box, line.decode("ascii"), CONTROL_S2C), self.login)

    def test_unicode_username_survives(self):
        message = {"type": "ERROR", "message": "Tên không hợp lệ"}
        self.assertEqual(open_control(self.box, seal_control(self.box, message, CONTROL_S2C), CONTROL_S2C), message)

    def test_line_is_single_line_and_hides_secrets(self):
        line = seal_control(self.box, self.login, CONTROL_S2C)
        self.assertNotIn(b"\n", line)
        for secret in (b"alice", b"token", self.login["token"].encode(), b"LOGIN_OK"):
            self.assertNotIn(secret, line)

    def test_same_message_gives_different_lines(self):
        self.assertNotEqual(seal_control(self.box, self.login, CONTROL_C2S),
                            seal_control(self.box, self.login, CONTROL_C2S))

    def test_direction_is_authenticated(self):
        line = seal_control(self.box, {"type": "PING"}, CONTROL_C2S)
        with self.assertRaises(DecryptError):
            open_control(self.box, line, CONTROL_S2C)  # client line replayed as server line

    def test_wrong_key_rejected(self):
        line = seal_control(self.box, self.login, CONTROL_S2C)
        with self.assertRaises(DecryptError):
            open_control(CryptoBox(os.urandom(32)), line, CONTROL_S2C)

    def test_tampered_line_rejected(self):
        line = bytearray(seal_control(self.box, self.login, CONTROL_S2C))
        middle = len(line) // 2
        line[middle] = ord("A") if line[middle] != ord("A") else ord("B")
        with self.assertRaises(DecryptError):
            open_control(self.box, bytes(line), CONTROL_S2C)

    def test_plain_json_and_garbage_rejected(self):
        for bad in (b'{"type":"LOGIN","username":"alice","udp_port":5}', b"not base64 !!", b"", b"AAAA", b"\xff\xfe"):
            with self.assertRaises(ValueError, msg=bad):  # DecryptError is a ValueError
                open_control(self.box, bad, CONTROL_C2S)

    def test_non_object_json_rejected(self):
        line = seal_control(self.box, [1, 2, 3], CONTROL_C2S)
        with self.assertRaises(ValueError):
            open_control(self.box, line, CONTROL_C2S)


class LoadKeyTests(unittest.TestCase):
    def _env(self, **values):
        env = {k: v for k, v in os.environ.items() if k != KEY_ENV_VAR}
        env.update(values)
        return mock.patch.dict(os.environ, env, clear=True)

    def test_key_from_env(self):
        key = os.urandom(32)
        with self._env(**{KEY_ENV_VAR: " " + key.hex() + "\n"}):
            self.assertEqual(load_key(), key)

    def test_key_from_file_with_bom_and_newline(self):
        key = os.urandom(32)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "local_key.txt"
            path.write_bytes(b"\xef\xbb\xbf" + key.hex().encode() + b"\r\n")
            with self._env(), mock.patch.object(crypto, "KEY_PATH", path):
                self.assertEqual(load_key(), key)

    def test_env_has_priority_over_file(self):
        env_key, file_key = os.urandom(32), os.urandom(32)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "local_key.txt"
            path.write_text(file_key.hex())
            with self._env(**{KEY_ENV_VAR: env_key.hex()}), mock.patch.object(crypto, "KEY_PATH", path):
                self.assertEqual(load_key(), env_key)

    def test_missing_key(self):
        with tempfile.TemporaryDirectory() as d:
            with self._env(), mock.patch.object(crypto, "KEY_PATH", Path(d) / "none.txt"):
                with self.assertRaises(RuntimeError):
                    load_key()

    def test_bad_hex_and_bad_length(self):
        with self._env(**{KEY_ENV_VAR: "zz" * 32}):
            with self.assertRaises(ValueError):
                load_key()
        with self._env(**{KEY_ENV_VAR: "ab" * 16}):
            with self.assertRaises(ValueError):
                load_key()


if __name__ == "__main__":
    unittest.main()