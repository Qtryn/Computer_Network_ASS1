"""Member 5: AES-GCM payload encryption, shared key supplied outside Git."""
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_PATH = Path(__file__).resolve().parents[2] / "config" / "local_key.txt"


def load_key():
    """Accept hex key via environment or config/local_key.txt (gitignored)."""
    value = os.environ.get("COLLAB_KEY", "").strip()
    if not value and KEY_PATH.exists():
        value = KEY_PATH.read_text(encoding="ascii").strip()
    if not value:
        raise RuntimeError("Missing AES key. First run: python scripts/generate_key.py")
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("COLLAB_KEY must be a hexadecimal AES key") from exc
    if len(key) != 32:
        raise ValueError("COLLAB_KEY must contain exactly 32 bytes (64 hex characters)")
    return key


class CryptoBox:
    def __init__(self, key):
        self.aes = AESGCM(key)

    def encrypt(self, plaintext, aad=b""):
        nonce = os.urandom(12)  # Fresh nonce for every encrypted UDP message.
        return nonce + self.aes.encrypt(nonce, plaintext, aad)

    def decrypt(self, ciphertext, aad=b""):
        if len(ciphertext) < 28:
            raise ValueError("Truncated AES-GCM ciphertext")
        nonce, encrypted = ciphertext[:12], ciphertext[12:]
        return self.aes.decrypt(nonce, encrypted, aad)
