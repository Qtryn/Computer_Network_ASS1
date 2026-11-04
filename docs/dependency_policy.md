# Dependency Policy

**Goal: teach socket programming, not hide it behind frameworks.**

| Package/module | Source | Purpose |
|---|---|---|
| `socket` | Python standard library | Direct TCP/UDP connection, send, receive, bind |
| `threading`, `queue`, `time` | Python standard library | 10–20 concurrent clients, stream workers, retry timers |
| `json`, `struct`, `uuid` | Python standard library | Handwritten packet framing and serialization |
| `hashlib`, `pathlib`, `os` | Python standard library | SHA-256 and safe file I/O |
| `socket` (HTTP adapter) | Python standard library | Minimal localhost HTTP handling with raw TCP sockets |
| `unittest` | Python standard library | Tests without installing pytest |
| **`cryptography`** | **Only third-party package** | **Standard AES-GCM encryption/decryption required by rubric** |

Not used: Flask, Django, FastAPI, requests, Socket.IO, WebSockets, protobuf,
QUIC frameworks, PyQt, SQL databases or cloud APIs.

The reliable UDP logic (sequence numbers, ACK, retransmission, reordering,
window) and file chunking/reassembly are implemented directly by the students.

**Instructor confirmation needed:** The UI serves only the four required HTTP endpoints
using raw TCP sockets and browser JavaScript. Confirm the expected HTTP UI
behavior before final submission.

Do not replace AES-GCM with XOR, Caesar cipher, homemade AES or an unreviewed
crypto scheme just to remove the single dependency: that would compromise
correctness and the rubric's requirement to use a standard cryptographic library.
