"""Generate one local shared AES key. Distribute it privately to team clients."""
import os
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "config" / "local_key.txt"
if path.exists():
    print(f"Key already exists at {path}. Not overwriting it.")
else:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(os.urandom(32).hex() + "\n", encoding="ascii")
    print(f"New local key created at {path} (DO NOT COMMIT).")
