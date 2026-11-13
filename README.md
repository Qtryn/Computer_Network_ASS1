# Network Collaboration Application

Assignment 1 - Distributed and Streaming-based Client-Server Collaboration Application.

A self-hosted collaboration application built with Python raw sockets. Multiple
clients connect to a central server to discover online users, exchange private or
broadcast messages, and transfer files. TCP/TLS carries authentication and session
control; a custom reliable UDP protocol carries encrypted chat and file chunks.
A local HTML/JavaScript interface shows connection state, delivery and file progress.

## Features

- Demo login or password-based Register, Login and Logout over verified TLS/HTTPS.
- Online user roster, private chat and broadcast to connected recipients.
- UDP sequencing, per-stream ordering, ACKs, retries and a fixed four-packet window.
- Streaming file chunks, receiver SHA-256 verification and a final file receipt.
- AES-256-GCM payload encryption and authenticated packet headers.
- Concurrent clients and separate chat/file streams.
- Per-account RAM outbox with ordered replay after reconnect and authentication.

`DELIVERED` means the recipient application acknowledged the chat; it is not a
human read receipt or durable storage guarantee. File success requires the
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
report/        Reserved for the team's final Technical Explanation Report PDF
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
.\.venv\Scripts\python.exe -m app.run_server --accounts config/local_accounts.json --tls-cert config/local_tls/server.pem --tls-key config/local_tls/server-key.pem
.\.venv\Scripts\python.exe -m app.run_client --name alice --ui-port 8011 --tls-ca config/local_tls/server.pem --ui-cert config/local_tls/server.pem --ui-key config/local_tls/server-key.pem
.\.venv\Scripts\python.exe -m app.run_client --name bob --ui-port 8012 --tls-ca config/local_tls/server.pem --ui-cert config/local_tls/server.pem --ui-key config/local_tls/server-key.pem
```

Open **https://127.0.0.1:8011** and **https://127.0.0.1:8012**. Register distinct
usernames (1-20 ASCII letters, digits or underscores) with nonblank 8-128 character
passwords. Registration does not log in automatically: enter the password again
and click **Login**. Click **Logout** to end a session. The account JSON store is
created by the first successful registration and contains salted PBKDF2 hashes.
The password field clears after each attempt; passwords are not saved for reconnect.

After server restart or connection loss, log in again with the same account to
resume its RAM outbox. Bring the recipient online before replaying pending chats.
Demo mode reconnects automatically; session expiration requires a fresh login.

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

Previously recorded local verification on **November 13, 2026** passed **65 Python
tests**, smoke checks and **20 concurrent localhost clients**. Real Chrome HTTPS
demonstrations passed registration/login, messaging, verified files and ordered
outbox replay. A real Wireshark capture verified repeated UDP DATA and its ACK.
These are recorded local results, not a guarantee for every machine or future run.
The JavaScript test uses a DOM double; it is separate from real browser testing.
Detailed experimental artifacts are retained by the team in a development archive
and can be provided on request; they are excluded from the submission tree.

Optional verification (generate the certificate before the Wireshark demo):

```powershell
.\.venv\Scripts\python.exe -m scripts.lossy_benchmark --help
.\.venv\Scripts\python.exe -m scripts.wireshark_demo
```

The Wireshark demo generates real TLS/UDP traffic with a lost ACK, verified file
and server restart. Capture loopback on TCP 9100/UDP 9101 while it runs. Use that
run's printed UUIDs; `tcp.analysis.retransmission` does not identify UDP retries.

## Known limitations

- The four-packet window is fixed flow limiting; **BBR/CUBIC is not implemented**.
- Outboxes and deduplication caches are bounded and RAM-only. Closing the local
  client process loses pending messages; durable chat history is not implemented.
- New chat composition is disabled while disconnected. Pending items must have
  been enqueued while connected; there is no offline message composition.
- Interrupted files are cleaned up rather than resumed; completed downloads remain.
- Two independent LAN hosts, very large files and long-duration runs were not tested.
- UDP peers share a demo AES key. There is no production key exchange or
  production-grade end-to-end encryption; transport ACKs themselves are unencrypted.
- The local browser adapter is intended for localhost use, not public hosting.

## Report

The final PDF will be added by the team in [report/](report/) as
`Technical_Explanation_Report.pdf`. Report editing and upload are pending separately;
this repository does not substitute a preview or an evidence-placeholder PDF.

## Team

| Contributor | Responsibility |
|---|---|
| Ta Tuan Khai | Server, authentication/session control, registry and routing |
| Dang Tuan Kiet | Reliable UDP transport, ACKs, retries, ordering and window |
| Nguyen Le Quang Truc | Chat/files, chunking, reassembly, SHA-256 and integration |
| Phan Thi Thanh Binh | Client and browser UI, connection state and transfer progress |
| Huynh Le Nghi Quan | AES-GCM, security tests, verification and packaging |
