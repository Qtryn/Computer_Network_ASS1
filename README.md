# Network Collaboration Application

Network Application Development — Assignment 1  
**Student starter project | Python 3.11+ | Five ownership areas**

A small self-hosted collaboration application built with **Python TCP/UDP sockets**.
The repository is runnable so the team can test integration while developing the
five modules. It is a **starter project, not a completed 10/10 submission**.

## 1. Minimal dependencies

- Python 3.11 or newer and Git.
- **One external package:** `cryptography` for standard AES-GCM encryption.
- All other Python modules are from the standard library (`socket`, `threading`,
  `json`, `struct`, `hashlib`, `unittest`, etc.).
- **No** Flask, Django, requests, WebSockets, Socket.IO, QUIC/UDP frameworks,
  database, GUI toolkit, or cloud services.

The course handout explicitly requires payload encryption using a standard
cryptographic library. Reimplementing AES from scratch is deliberately avoided:
it would be harder to review and much easier to get wrong. The **application
protocol, UDP ACK/retry/window, file splitting and reassembly are handwritten.**

The local browser HTTP adapter is also implemented with `socket.socket`,
bound only to `127.0.0.1`. No HTTP server library is used.

## 2. Setup — Windows PowerShell

From the project root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/generate_key.py
```

**To avoid activation-policy problems**, the commands above call the virtual
Python executable directly. For the remaining examples, `python` means this
virtual environment's Python: either activate it or replace `python` with
`.\.venv\Scripts\python.exe`.

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/generate_key.py
```

## 3. Run a localhost demo

Run in **three separate terminals** from the project root:

```powershell
python -m app.run_server
```

```powershell
python -m app.run_client --name alice --ui-port 8011
```

```powershell
python -m app.run_client --name bob --ui-port 8012
```

Open `http://127.0.0.1:8011` (Alice) and `http://127.0.0.1:8012` (Bob).
Select Bob, send a private message or a file, and inspect `downloads/bob/`.
For broadcast chat select **Everyone**. Use Ctrl+C to stop each process.

TCP port: **9100**; UDP port: **9101**. See `docs/getting_started.md`
for localhost, LAN, and troubleshooting notes.

## 4. Run tests

```powershell
python -m unittest discover -s tests -v
python scripts/smoke_test.py
python scripts/load_test.py
```

The integration tests use real localhost sockets. LAN, high-loss, large-file
and long-running tests are still required before final submission.

## 5. Team ownership and readable folders

| Member | Folder(s) | Responsibility |
|---|---|---|
| Member 1 | `app/server/`, `app/run_server.py` | TCP login, server, user registry, routing |
| Member 2 | `app/transport/` | Reliable UDP, ACK, sequence, retry, window |
| **Member 3** | **`app/features/`**, `tests/test_features.py` | **Chat, file chunking, reassembly, SHA-256** |
| Member 4 | `app/web/`, `app/client.py`, `app/run_client.py` | Client and simple browser UI |
| Member 5 | `app/security/`, tests and scripts | Encryption, testing, documentation, packaging |

The shared `app/common/` folder belongs to the **whole group**; protocol/API
changes must be agreed before merging. Keep changes on separate Git branches.

## 6. Project documentation

- `docs/getting_started.md`: basic setup, demo and common errors
- `docs/member3_guide.md`: exactly what Member 3 should edit and test
- `docs/git_workflow.md`: five-person push/pull and pull request workflow
- `docs/architecture.md`: module and networking diagram
- `docs/protocol.md`: packet and message definitions
- `docs/member_tasks.md`: next actions per member
- `docs/dependency_policy.md`: why the project has only one external package
- `docs/rubric_checklist.md`: current progress against all ten rubric points
- `docs/test_plan.md`: repeatable test scenarios
- `docs/report_outline.md`: report requirements

## 7. Current limitations (do not hide in a report)

- The TCP login uses usernames plus a temporary session token; it does not
  implement password-based account verification or encrypted TCP login.
- AES-GCM is applied to **UDP DATA payloads** with one pre-shared test key.
  This is not a production key-exchange system.
- UDP has ordered delivery, ACK/retry and a fixed window, but **BBR/CUBIC
  congestion control is not implemented**. Confirm required scope with lecturer.
- File transfer works for the localhost demo; cancellation/timeout cleanup,
  very large files, reconnections and highly lossy LAN conditions need work.
- The browser UI uses a raw-socket localhost HTTP adapter; do not expose it to the Internet.
- Original project statement says individual/pair, while this allocation has
  five members. Confirm authorized group size and the official deadline.

`config/local_key.txt`, downloads, caches and `.venv/` are intentionally excluded
from Git and from the distributed ZIP.
