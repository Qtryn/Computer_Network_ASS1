# Network Collaboration Application

Assignment 1 - Distributed and Streaming-based Client-Server Collaboration Application.

A self-hosted collaboration application built with Python raw sockets. Multiple
clients connect to a central server to discover online users, exchange private or
broadcast messages, and transfer files. TCP/TLS carries authentication and session
control and offline chat synchronization; a custom reliable UDP protocol carries
live encrypted chat and file chunks.
A local HTML/JavaScript interface shows connection state, delivery and file progress.

## Features

- Demo login or password-based Register, Login and Logout over verified TLS/HTTPS.
- Online user roster, private chat and broadcast to connected recipients.
- UDP sequencing, per-stream ordering, authenticated ACKs and selective retries.
- Receiver-advertised credit and bounded AIMD (one to four packets per stream).
- Streaming file chunks, receiver SHA-256 verification and a final file receipt.
- AES-256-GCM payload encryption and authenticated packet headers.
- Concurrent clients and separate chat/file streams.
- Per-account SQLite outbox/inbox and server relay storage in account mode.
- Offline chat composition after authentication, stable-ID replay and durable deduplication.
- Optional authenticated direct peer chat and persistent channel membership.

`DELIVERED` means the recipient application acknowledged the chat; it is not a
human read receipt. In account mode, receivers commit chat to SQLite before
acknowledging it. File success requires the
receiver's SHA-256 check and `FILE_RECEIPT`, beyond transport ACKs.

## Technologies and structure

Python standard library (`socket`, `ssl`, `threading`, `json`, `struct`, `hashlib`),
`cryptography` for AES-GCM/certificates, and browser HTML/JavaScript. Networking,
HTTP parsing, packet framing and reliability are implemented directly with sockets.

```text
app/           Client/server entry points, protocol, transport, features, security, UI
scripts/       Key/certificate generation, smoke/load/UI tests and optional demos
tests/         Unit and real-socket integration regressions
docs/          Architecture and custom protocol specification
report/        Final Technical Explanation Report PDF
config/        Local generated key, TLS certificate/key and account store (gitignored)
```

See [architecture](docs/architecture.md) and [protocol specification](docs/protocol.md).

## Requirements

- Python **3.11+**; the recorded Windows verification used Python **3.14.5**.
- Install `requirements.txt`: `cryptography>=43,<47` is the only direct dependency.
- A browser for the UI; Node.js for the optional JavaScript logic tests.
- Wireshark/Npcap is optional for inspecting actual network traffic.

## Quick start - demo mode

Run from the repository root in Windows PowerShell. No environment activation is needed.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/generate_key.py
```

Run each command in a separate terminal, keeping the repository as the working directory:

```powershell
# Terminal 1: server (TCP 9100, UDP 9101)
.\.venv\Scripts\python.exe -m app.run_server
# Terminal 2: Alice's local UI
.\.venv\Scripts\python.exe -m app.run_client --name alice --ui-port 8011
# Terminal 3: Bob's local UI
.\.venv\Scripts\python.exe -m app.run_client --name bob --ui-port 8012
```

Open <http://127.0.0.1:8011> and <http://127.0.0.1:8012>, then click **Login** on
both pages. These commands use passwordless demo mode. Choose Bob for a private
message/file or **Everyone** for broadcast chat. Use the actual file chooser and
wait for receiver verification; completed files are in `downloads/<recipient>/`.
Logout ends the network session while leaving the local UI available. Use Ctrl+C
to stop each process.

On Linux/macOS, create the environment with `python3 -m venv .venv` and replace
`.\.venv\Scripts\python.exe` with `.venv/bin/python` in the commands above and below.

## Secure account mode

Stop the demo server before using the same ports. Generate a localhost certificate once:

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_cert
```

The generated certificate covers `localhost` and `127.0.0.1` and expires after
30 days. Configure browser/OS trust for this locally generated certificate manually,
or provide an already trusted localhost certificate. Open the HTTPS pages only
after normal certificate verification succeeds; never bypass warnings or disable
verification. The application does not change the OS certificate store.

Start these in three separate terminals:

```powershell
.\.venv\Scripts\python.exe -m app.run_server --accounts config/local_accounts.json --chat-db config/relay.sqlite3 --tls-cert config/local_tls/server.pem --tls-key config/local_tls/server-key.pem
.\.venv\Scripts\python.exe -m app.run_client --name alice --ui-port 8011 --state-db config/alice.sqlite3 --tls-ca config/local_tls/server.pem --ui-cert config/local_tls/server.pem --ui-key config/local_tls/server-key.pem
.\.venv\Scripts\python.exe -m app.run_client --name bob --ui-port 8012 --state-db config/bob.sqlite3 --tls-ca config/local_tls/server.pem --ui-cert config/local_tls/server.pem --ui-key config/local_tls/server-key.pem
```

Open **https://127.0.0.1:8011** and **https://127.0.0.1:8012**. Register distinct
usernames (1-20 ASCII letters, digits or underscores) with nonblank 8-128 character
passwords. Registration does not log in automatically: enter the password again
and click **Login**. Click **Logout** to end a session. The account JSON store is
created by the first successful registration and contains salted PBKDF2 hashes.
The password field clears after each attempt; passwords are not saved for reconnect.

After server restart or connection loss, log in again with the same account to
resume its SQLite outbox, including after closing and reopening the client process.
Keep the same database paths. A disconnected authenticated profile can queue chat
to known contacts; files require a live connection. Logout clears the visible
history and revokes the browser session, while retaining the owner's pending chats
on disk. Delivery waits for every intended recipient's application confirmation.
Demo mode uses RAM and reconnects automatically; session expiration requires a fresh login.
Cookies have a separate name for each UI port so two localhost tabs stay independent.

The certificate/key reuse above is for processes on **one machine**. On separate
LAN hosts, keep the collaboration server's private key on that server; give each
local UI its own locally trusted certificate/key. Copy only the server's public
CA/certificate for `--tls-ca` and distribute the same AES test key privately.
Use `--host SERVER_IP --server-name CERTIFICATE_DNS_NAME` for verified server TLS.
The browser always connects to its own local UI, which binds to `127.0.0.1`.
For LAN use, bind the server with `--host 0.0.0.0` and allow TCP 9100/UDP 9101
on the server's private network. Separate-host LAN operation remains unverified.

## Testing

Run from the project root after installing dependencies and generating the AES key:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.smoke_test
.\.venv\Scripts\python.exe -m scripts.load_test
node scripts/test_ui.cjs
```

The latest recorded full-suite verification on **November 18, 2026** passed
**98 Python tests** and **20 concurrent localhost clients**. Separate recorded runs
also passed smoke checks, JavaScript UI checks, and AIMD/receiver-credit checks.
The suite includes
actual CLI processes with verified HTTPS, a shared browser-style cookie jar,
SQLite recovery after client/server restarts, concurrent files, fault injection,
forged ACK rejection, receiver backpressure and AIMD recovery. A new real Wireshark
capture on TCP 9100/UDP 9101 recorded 389 packets with no capture drops, including
byte-identical UDP retransmission and an encrypted 76-byte ACK.
The JavaScript test uses a DOM double. Separate **Chrome HTTPS account-mode checks
passed** registration/login, private/broadcast chat, file transfer with receiver
SHA-256 verification, and Logout. Two offline-composed messages retained their
stable IDs across complete client/server restarts; after password reauthentication,
both became DELIVERED, the pending count fell from two to zero, and each appeared
once in the recipient inbox. An independent-stream experiment also delivered chat
while a file-stream gap remained, followed by successful file verification.
Detailed experimental artifacts are retained by the team in a development archive
and can be provided on request; they are excluded from the submission tree.

Optional verification (generate the certificate before the Wireshark demo):

```powershell
.\.venv\Scripts\python.exe -m scripts.lossy_benchmark --help
.\.venv\Scripts\python.exe -m scripts.flow_demo
.\.venv\Scripts\python.exe -m scripts.wireshark_demo
```

The Wireshark demo generates real TLS/UDP traffic with a lost ACK, verified file
and server restart. Capture loopback on TCP 9100/UDP 9101 while it runs. Use that
run's printed UUIDs; `tcp.analysis.retransmission` does not identify UDP retries.

## Known limitations

- Congestion control is simple tested **AIMD**, not BBR/CUBIC; no adaptive pacing
  or bandwidth estimator is implemented. The supplied lecturer clarification allows this.
- SQLite is local plaintext storage protected by the OS profile. Account isolation
  is enforced by the application, not against another process that can read its DB.
  Pending queues and displayed history are bounded; stored history has no retention purge.
- Demo mode remains RAM-only. Offline composition requires a previously authenticated
  profile and known recipients; account-mode reconnect requires a password again.
- Interrupted files are cleaned up rather than resumed; completed downloads remain.
- Two independent LAN hosts, very large files and long-duration runs were not tested.
- UDP peers share a demo AES key. There is no production key exchange or
  production-grade end-to-end encryption. DATA and transport ACKs use AES-GCM;
  direct chat additionally validates a session-pair HMAC capability issued over TLS.
- The local browser adapter is intended for localhost use, not public hosting.

## Report

The final [Technical Explanation Report](report/Technical_Explanation_Report.pdf)
covers the architecture, custom protocol, messaging and file-transfer workflows,
recorded test results, experimental evidence, and implementation limitations.

## Team

| Contributor | Responsibility |
|---|---|
| Ta Tuan Khai | Server, authentication/session control, registry and routing |
| Dang Tuan Kiet | Reliable UDP transport, ACKs, retries, ordering and window |
| Nguyen Le Quang Truc | Chat/files, chunking, reassembly, SHA-256 and integration |
| Phan Thi Thanh Binh | Client and browser UI, connection state and transfer progress |
| Huynh Le Nghi Quan | AES-GCM, security tests, verification and packaging |
