"""Member 5: AES-256-GCM payload encryption, shared key supplied outside Git.

Wire format : nonce (12 bytes) || ciphertext || tag (16 bytes)
Overhead    : OVERHEAD = 28 bytes per encrypted message. Transport/file code must
              subtract it from the datagram payload limit (see max_plaintext_size).
Key         : 32 random bytes (64 hex chars) from env COLLAB_KEY or
              config/local_key.txt (gitignored, created by scripts/generate_key.py).
Errors      : any failed decryption raises DecryptError, which subclasses both
              cryptography's InvalidTag and ValueError, so existing callers that
              catch either one keep working.
"""
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
