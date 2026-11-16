# Network Collaboration Application

Assignment 1 for CO3094. Python and browser JavaScript connect registered users for
private and broadcast chat, channels and verified file transfers. The server tracks
sessions and coordinates discovery. Live chat can go directly between peers, and
the relay stores pending messages for offline delivery.

## Run on one Windows machine

Use Python 3.11+ and a browser. Run from the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.generate_key
.\.venv\Scripts\python.exe -m scripts.generate_cert
```

For this localhost demo, trust the generated public certificate
`config/local_tls/server.pem` in a local test browser profile or use an existing
trusted certificate. Never distribute the private key. Start these commands in
three terminals:

```powershell
.\.venv\Scripts\python.exe -m app.run_server
.\.venv\Scripts\python.exe -m app.run_client --ui-port 8011 --state-db config/local_alice.sqlite3
.\.venv\Scripts\python.exe -m app.run_client --ui-port 8012 --state-db config/local_bob.sqlite3
```

Open **https://127.0.0.1:8011** and **https://127.0.0.1:8012**. Register two new
usernames and passwords, then log in. Choose the other user for a private chat or
a file. Select **Everyone** for broadcast. To use a channel, join the same named
channel on both pages, then select it as the destination. Message history and
delivery status are visible in the scrollable feed. Files are written to
`downloads/<recipient>/` after validation.

For recovery, stop the server. After the connection status changes, send a message
to the other user. The page will report that the server is unavailable and the
chat is saved. Stop the sender's Python process, restart the server and client
using the same data paths, and log in as the same accounts. The sender replays
pending chats and the receiver restores messages by ID. The browser does not keep
the account password. Deleting the SQLite files deletes their persisted data.

The secure mode is the default. Both launchers accept `--demo` for the explicit
passwordless, in-memory test mode. Read `--help` for file, host and port overrides.
On Linux replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

## Linux raw TCP HTTP

The Windows launcher uses the kernel TCP listener for browser requests. The
Linux option `--raw-http` runs the same HTTPS routes over a user-space IPv4 TCP
listener. It is intended for an isolated network namespace on loopback. With
`iproute2`, `iptables` and the Python venv available:

```sh
sudo unshare --net sh
ip link set lo up
iptables -A OUTPUT -p tcp --sport 28081 --tcp-flags RST RST -j DROP
.venv/bin/python -B -m scripts.check_raw_http
exit
```

The namespace-local rule isolates kernel-generated TCP resets for the dedicated
lab port. The checker exercises the complete TLS and HTTP path from a conventional
HTTPS client. For the UI itself, run the launcher in that namespace with
`--raw-http --ui-port 28081` and use a browser in the same namespace.

## LAN and verification

Bind the tracker to its LAN IP or `0.0.0.0` with `--host`. Give clients its IP
via `--host` and the hostname in the server certificate via `--server-name`.
Use a trusted server certificate and only distribute its public trust material.
Each client uses its own local UI certificate and private key. Pass the shared
UDP test key privately. Allow TCP 9100 and UDP 9101 to the tracker on the private
LAN, and peer-to-peer UDP for direct chat. If peers cannot reach each other,
their chats can use the relay. The browser UI listens on localhost.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.smoke_test
.\.venv\Scripts\python.exe -m scripts.load_test
node scripts/test_ui.cjs
.\.venv\Scripts\python.exe -m scripts.lossy_benchmark --help
.\.venv\Scripts\python.exe -m scripts.wireshark_demo
```

When capturing with Wireshark/Npcap, select the loopback interface. Use
`tcp.port == 9100 || udp.port == 9101 || udp.payload[0:4] == 43:4f:4c:42`.
The demo prints the UUID of the repeated UDP DATA and the file stream UUID.
The UDP header is visible while DATA and ACK credit are authenticated and
encrypted. The capture and matching application log are both needed to show file
verification and recipient delivery.

See [architecture](docs/architecture.md), [protocol](docs/protocol.md) and the
[technical report](report/Technical_Explanation_Report.pdf).

## Team

| Contributor | Responsibility |
|---|---|
| Ta Tuan Khai | Server, authentication/session control, registry and routing |
| Dang Tuan Kiet | Reliable UDP transport, ACKs, retries, ordering and window |
| Nguyen Le Quang Truc | Chat/files, chunking, reassembly, SHA-256 and integration |
| Phan Thi Thanh Binh | Client and browser UI, connection state and transfer progress |
| Huynh Le Nghi Quan | AES-GCM, security tests, verification and packaging |
