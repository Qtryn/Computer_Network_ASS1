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

Open `http://127.0.0.1:8011` (Alice) and `http://127.0.0.1:8012` (Bob),
then press **Login** on each page. These commands use **Demo / no password** mode.
Select Bob, send a private message or a file, and inspect `downloads/bob/`.
For broadcast chat select **Everyone**. Use Ctrl+C to stop each process.

TCP port: **9100**; UDP port: **9101**. See `docs/getting_started.md`
for localhost, LAN, and troubleshooting notes.

### Password accounts and verified TLS (localhost)

Provision accounts once; the CLI prompts for passwords without echoing them.
Only salted PBKDF2-HMAC-SHA256 hashes are saved in the gitignored account file.

```powershell
.\.venv\Scripts\python.exe -m app.server.auth alice
.\.venv\Scripts\python.exe -m app.server.auth bob
.\.venv\Scripts\python.exe -m scripts.generate_cert
```

The generated certificate covers `localhost` and `127.0.0.1`, lasts 30 days,
and is for a local demo. For the browser, trust this locally generated certificate
in your browser/OS, or supply an already trusted localhost certificate. Do not
bypass certificate errors or disable verification. Trust installation is a manual
setup step; the application does not change the OS certificate store.

Run these in three terminals:

```powershell
.\.venv\Scripts\python.exe -m app.run_server --accounts config/local_accounts.json --tls-cert config/local_tls/server.pem --tls-key config/local_tls/server-key.pem
```

```powershell
.\.venv\Scripts\python.exe -m app.run_client --name alice --ui-port 8011 --tls-ca config/local_tls/server.pem --ui-cert config/local_tls/server.pem --ui-key config/local_tls/server-key.pem
```

```powershell
.\.venv\Scripts\python.exe -m app.run_client --name bob --ui-port 8012 --tls-ca config/local_tls/server.pem --ui-cert config/local_tls/server.pem --ui-key config/local_tls/server-key.pem
```

Open **https://127.0.0.1:8011** and **https://127.0.0.1:8012** and enter the
provisioned username/password. Account mode requires HTTPS on the local adapter
as well as verified TLS to the collaboration server, protecting passwords on
both TCP hops. Passwords are never stored in browser storage, logs, or client
attributes. The password field is cleared after every login attempt.

The shared certificate/key commands above are for processes on **one machine**.
For separate LAN machines, generate each local UI's own certificate/key and
trust it locally; copy only the collaboration server's public CA/certificate to
clients for `--tls-ca`. Keep the server's private key on the server. Use
`--host SERVER_IP --server-name CERTIFICATE_DNS_NAME` when the server certificate
identifies a DNS name. All participants need the same privately distributed AES key.

**Logout** sends LOGOUT, closes TCP/UDP and heartbeat, clears this client's RAM
events and browser feed, resets recipients/progress, and leaves the local web
listener running. Press Login again for a new token and empty chat history.
Other clients' history and successfully downloaded files are preserved.

## 4. Run tests

```powershell
python -m unittest discover -s tests -v
python -m scripts.smoke_test
python -m scripts.load_test
# Optional JavaScript logic checks; Node is a test tool, not an app dependency:
node scripts/test_ui.cjs
```

The integration tests use real localhost TCP/UDP and TLS sockets. They cover
password errors, certificate validation, logout/relogin, revoked tokens, empty/
text/binary files, SHA-256, disconnect/timeout cleanup, malformed messages,
loss/duplicates/reordering, and chat during file transfer. The load script keeps
20 clients connected. The JavaScript test uses a DOM double, not a real browser.
See `docs/test_plan.md` for the remaining manual browser/LAN checklist.

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

- Demo mode uses usernames and temporary tokens. Account mode requires passwords,
  verified server TLS, and local browser HTTPS; no automatic password fallback.
- AES-GCM is applied to **UDP DATA payloads** with one pre-shared test key.
  This is not a production key-exchange system.
- UDP has ordered delivery, ACK/retry and a fixed window, but **BBR/CUBIC
  congestion control is not implemented**. Confirm required scope with lecturer.
- Interrupted transfers expire after 60 seconds without relay activity or when a
  participant's session disappears/changes. Clients remove partial `.part` files
  after an abort, logout, or local inactivity timeout; completed files stay intact.
- A UDP timeout means delivery is uncertain. The next send on that stream first
  retransmits retained frames with their original IDs/sequences. Late duplicates
  cannot deliver twice. Re-entering the same chat text creates a new message.
- Chat's outgoing line reports a server ACK; a separate receipt reports recipient
  transport ACKs, not that a person read it. File success needs FILE_RECEIPT after
  receiver SHA-256 verification.
- Browser automation could not initialize in this environment. Actual browser
  rendering, browser certificate trust, LAN, very large files and long-running
  tests remain manual checks. BBR/CUBIC remains unimplemented.
- The browser UI uses a raw-socket localhost HTTP adapter; do not expose it to the Internet.
- Original project statement says individual/pair, while this allocation has
  five members. Confirm authorized group size and the official deadline.

`config/local_key.txt`, downloads, caches and `.venv/` are intentionally excluded
from Git and from the distributed ZIP.
