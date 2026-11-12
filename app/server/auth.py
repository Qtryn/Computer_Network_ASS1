"""Local password accounts and thread-safe login throttling for TV1."""

import argparse
import getpass
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


USERNAME = re.compile(r"[A-Za-z0-9_]{1,20}")
ITERATIONS = 600_000


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)


def read_accounts(path):
    records = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(records, dict):
        raise ValueError("Account file must contain a JSON object")
    for name, record in records.items():
        if not USERNAME.fullmatch(name) or not isinstance(record, dict):
            raise ValueError("Invalid account record")
        for key, size in (("salt", 16), ("hash", 32)):
            value = record.get(key)
            if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-fA-F]{{{size * 2}}}", value):
                raise ValueError(f"Invalid account {key}")
    return records


@dataclass
class Account:
    salt: bytes
    digest: bytes
    failures: int = 0
    locked_until: float = 0.0
    lock: object = field(default_factory=threading.Lock, repr=False)


class PasswordAccounts:
    def __init__(self, records, *, max_attempts=3, lock_seconds=60, clock=time.monotonic,
                 path=None):
        if max_attempts < 1 or lock_seconds <= 0:
            raise ValueError("Login limits must be positive")
        self.accounts = {name: Account(bytes.fromhex(record["salt"]), bytes.fromhex(record["hash"]))
                         for name, record in records.items()}
        self.unknown_account = Account(secrets.token_bytes(16), secrets.token_bytes(32))
        self.max_attempts = max_attempts
        self.lock_seconds = lock_seconds
        self.clock = clock
        self.path = Path(path) if path is not None else None
        self.records = {name: dict(record) for name, record in records.items()}
        self.store_lock = threading.Lock()

    def register(self, username, password):
        if self.path is None:
            raise ValueError("Registration requires a persistent account file")
        if not isinstance(username, str) or not USERNAME.fullmatch(username):
            raise ValueError("Username: 1-20 letters, digits or underscores")
        if not isinstance(password, str) or not 8 <= len(password) <= 128 or not password.strip():
            raise ValueError("Password must contain 8-128 characters and not be blank")
        salt = secrets.token_bytes(16)
        digest = hash_password(password, salt)
        with self.store_lock:
            if username in self.accounts:
                raise ValueError("Username already exists")
            records = {**self.records, username: {"salt": salt.hex(), "hash": digest.hex()}}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".accounts-", delete=False) as out:
                temporary = Path(out.name)
                try:
                    json.dump(records, out, indent=2)
                    out.write("\n")
                    out.flush()
                    os.fsync(out.fileno())
                except Exception:
                    out.close()
                    temporary.unlink(missing_ok=True)
                    raise
            try:
                temporary.replace(self.path)
            finally:
                temporary.unlink(missing_ok=True)
            self.records = records
            self.accounts[username] = Account(salt, digest)

    def verify(self, username, password):
        """Return a failure response or None on successful verification."""
        if not isinstance(password, str) or not password:
            raise ValueError("A password is required")
        with self.store_lock:
            account = self.accounts.get(username)
        state = account if account is not None else self.unknown_account
        with state.lock:
            now = self.clock()
            if now < state.locked_until:
                return {"type": "LOGIN_LOCKED", "retry_after_seconds": math.ceil(state.locked_until - now)}
            if state.locked_until:
                state.failures = 0
                state.locked_until = 0.0
            matches = hmac.compare_digest(hash_password(password, state.salt), state.digest)
            if account is not None and matches:
                state.failures = 0
                return None
            state.failures += 1
            if state.failures >= self.max_attempts:
                state.locked_until = self.clock() + self.lock_seconds
                return {"type": "LOGIN_LOCKED", "retry_after_seconds": math.ceil(self.lock_seconds)}
            return {"type": "LOGIN_FAIL", "remaining_attempts": self.max_attempts - state.failures}


def main():
    parser = argparse.ArgumentParser(description="Add a password account to a local JSON file")
    parser.add_argument("username")
    parser.add_argument("--file", type=Path, default=Path("config/local_accounts.json"))
    args = parser.parse_args()
    if not USERNAME.fullmatch(args.username):
        parser.error("Username: 1-20 letters, digits or underscores")
    records = read_accounts(args.file) if args.file.exists() else {}
    if args.username in records:
        parser.error("Username already exists")
    password = getpass.getpass("Password: ")
    if not password or password != getpass.getpass("Repeat password: "):
        parser.error("Passwords must be non-empty and match")
    salt = secrets.token_bytes(16)
    records[args.username] = {"salt": salt.hex(), "hash": hash_password(password, salt).hex()}
    args.file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.file.parent,
                                     prefix=".accounts-", delete=False) as out:
        temporary = Path(out.name)
        json.dump(records, out, indent=2)
        out.write("\n")
    try:
        temporary.replace(args.file)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Saved account {args.username} in {args.file}")


if __name__ == "__main__":
    main()
