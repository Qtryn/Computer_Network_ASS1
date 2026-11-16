import base64
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_SIZE = 32
NONCE_SIZE = 12
TAG_SIZE = 16
OVERHEAD = NONCE_SIZE + TAG_SIZE  # 28

KEY_ENV_VAR = "COLLAB_KEY"
KEY_PATH = Path(__file__).resolve().parents[2] / "config" / "local_key.txt"


CONTROL_C2S = b"collab-tcp-c2s"
CONTROL_S2C = b"collab-tcp-s2c"


class DecryptError(InvalidTag, ValueError):
    """Wrong key, tampered data/header (AAD), or truncated ciphertext."""


def load_key():
    """Accept hex key via environment or config/local_key.txt (gitignored)."""
    value = os.environ.get(KEY_ENV_VAR, "").strip()
    if not value and KEY_PATH.exists():
        # utf-8-sig tolerates the BOM that Windows editors sometimes add.
        value = KEY_PATH.read_text(encoding="utf-8-sig").strip()
    if not value:
        raise RuntimeError(
            f"Missing AES key. Set {KEY_ENV_VAR} or run: python scripts/generate_key.py")
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{KEY_ENV_VAR} must be a hexadecimal AES key") from exc
    if len(key) != KEY_SIZE:
        raise ValueError(
            f"{KEY_ENV_VAR} must contain exactly {KEY_SIZE} bytes ({KEY_SIZE * 2} hex characters)")
    return key


def max_plaintext_size(max_payload):
    """Largest plaintext whose encrypted form still fits in `max_payload` bytes."""
    return max(0, max_payload - OVERHEAD)


class CryptoBox:
    def __init__(self, key):
        if not isinstance(key, (bytes, bytearray)) or len(key) != KEY_SIZE:
            raise ValueError(f"AES key must be exactly {KEY_SIZE} bytes")
        self.aes = AESGCM(bytes(key))

    def encrypt(self, plaintext, aad=b""):
        nonce = os.urandom(NONCE_SIZE)  # Fresh nonce for every encrypted UDP message.
        return nonce + self.aes.encrypt(nonce, bytes(plaintext), bytes(aad))

    def decrypt(self, ciphertext, aad=b""):
        if len(ciphertext) < OVERHEAD:
            raise DecryptError("Truncated AES-GCM ciphertext")
        nonce, encrypted = bytes(ciphertext[:NONCE_SIZE]), bytes(ciphertext[NONCE_SIZE:])
        try:
            return self.aes.decrypt(nonce, encrypted, bytes(aad))
        except InvalidTag:
            raise DecryptError("Wrong key, or data/header was modified") from None


def seal_control(box, message, direction):
    """dict -> encrypted TCP control line (bytes, WITHOUT the trailing newline)."""
    plain = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(box.encrypt(plain, direction))


def open_control(box, line, direction):
    """Encrypted TCP control line -> dict. Raises DecryptError (a ValueError) if invalid."""
    line = line.encode("ascii") if isinstance(line, str) else bytes(line)
    try:
        blob = base64.b64decode(line.strip(), validate=True)
    except ValueError:
        raise DecryptError("Control line is not valid base64") from None
    message = json.loads(box.decrypt(blob, direction))
    if not isinstance(message, dict):
        raise ValueError("Control message must be a JSON object")
    return message