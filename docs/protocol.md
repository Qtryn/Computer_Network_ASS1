# Protocol specification (version 1)

The control and UDP message contracts below describe the submitted implementation.

## 1. TCP control (one JSON object + `\n` per message)

Client -> server:

```json
{"type":"HELLO","version":1}
{"type":"LOGIN","username":"alice","udp_port":54321}
```

Server -> client:

```json
{"type":"LOGIN_OK","token":"<random-session-token>","chat_stream":"<session-derived-uuid>","users":["alice","bob"],"version":2,"udp_port":9101}
```

HELLO receives `HELLO_OK`; then LOGIN is sent. In account mode the connection
uses verified TLS and LOGIN includes `password` (never persist it). Rejections
include `LOGIN_FAIL`, `LOGIN_LOCKED` or `ERROR`. Demo mode also accepts the
legacy LOGIN-first handshake, but never accepts a password. Other control
messages include `PING`, `GET_USERS`, `GET_PEERS`, `SYNC_CHAT`, `JOIN_CHANNEL`,
`GET_CHANNELS`, `LOGOUT`, `AUTH_REQUIRED`, and `ERROR`. TCP uses newline-delimited
JSON framing because `recv()` alone does not preserve message boundaries.
One active session per username. Account records store salted PBKDF2-SHA256
hashes; account mode requires a server TLS context. Expired sessions require
re-authentication. LOGOUT/TCP EOF revokes the token and updates the roster.
The client closes its network session and clears events; relogin uses a new
client/token while the local HTTP(S) listener remains available.

After HELLO_OK, an unauthenticated **TLS account-mode** connection may send
`{"type":"REGISTER","username":"alice","password":"..."}` and receives
REGISTER_OK or ERROR, then closes. Registration requires the configured persistent
JSON store; username/password validation and atomic writes share the account lock.
Credentials never travel over demo/plain TCP, or over plain HTTP in account mode.

```mermaid
stateDiagram-v2
    [*] --> LoggedOut
    LoggedOut --> Handshake: Login (verified TLS in account mode)
    Handshake --> LoggedOut: HELLO or LOGIN rejected
    Handshake --> Active: HELLO_OK then LOGIN_OK
    Active --> LoggedOut: LOGOUT / EOF / expired token
    LoggedOut --> LoggedOut: clear events, stop UDP and heartbeat
```

## 2. UDP frame bytes

| Field | Bytes | Meaning |
|---|---:|---|
| Magic `COLB` | 4 | Protocol recognition |
| Version | 1 | `1` |
| Kind | 1 | `1=DATA`, `2=ACK` |
| Sequence | 4 | Big endian unsigned integer, starts at 0 per (peer,stream) |
| Packet ID | 16 | UUID; ACK references exactly this packet |
| Stream ID | 16 | Session-derived chat/ACK UUID; file uses file UUID (`...0001` remains a legacy sentinel) |
| Payload | variable | DATA and ACK: 12-byte nonce + AES-GCM ciphertext (includes 16-byte authentication tag) |

Header size: **42 bytes**. Maximum UDP datagram: **1200 bytes**.
An ACK is **76 bytes**: 42-byte header, 12-byte nonce, six encrypted bytes and a
16-byte authentication tag. Its plaintext is `[2-byte free receiver credit]
[4-byte increasing credit revision]`, both unsigned big endian. Reordered ACK
snapshots cannot replace a newer credit revision. The AES-GCM AAD is the complete
header for both DATA and ACK. Bare, malformed, tampered and wrong-key ACKs fail.

The encrypted application message contains:

```
[2-byte metadata JSON length][UTF-8 JSON metadata][optional raw file bytes]
```

Only file chunks have raw binary data; no base64 expansion inside messages.
All UDP DATA and ACK payloads are encrypted and authenticated by the shared
AES-GCM key. A new 12-byte random nonce is generated for newly encrypted frames.
Retransmission repeats the identical ciphertext, UUID and sequence. Never encrypt
different plaintext with a reused nonce/key pair.

## 3. UDP application message types

| Type | Required fields | Meaning |
|---|---|---|
| `USERS` | `users, version` | Server updates online usernames (monotonic version avoids stale updates) |
| `CHAT` | `sender, recipient, text, message_id, targets` | Stable UUID and fixed recipient snapshot; private targets must equal `[recipient]` |
| `CHAT_ACK` | `sender, original_sender, message_id` | Authenticated recipient application accepted this chat |
| `CHAT_RECEIPT` | `message_id, status, recipients, message` | PENDING or DELIVERED; delivered only after every target's application ACK |
| `FILE_START` | `file_id, sender, recipient, name, size, total_chunks, chunk_size, sha256` | Announce file and expected hash |
| `FILE_CHUNK` | `file_id, sender, recipient, index, data` | Binary file chunk, starts at index 0 |
| `FILE_END` | `file_id, sender, recipient` | File transmission finished |
| `FILE_RECEIPT` | `file_id, sender, status, message` | Receiver confirms complete hash check or error |
| `FILE_ABORT` | `file_id, message` | Server cancels interrupted/expired transfer; remove only its partial file |
| `ERROR` | `message` | Application error response |

Client -> server messages add `token` containing the authenticated session token.
Server -> client messages intentionally omit token. `data` is a Python `bytes`
field that becomes the raw byte suffix of the encrypted application message.
A file stream uses the file's `file_id` as its Stream ID.
Chat/control uses `UUID(SHA256("chat:" + session_token)[:16])`; CHAT_ACK uses
the same derivation with `"ack:"`. The token itself is not exposed in the header.
Both endpoints derive these IDs after LOGIN_OK. A fresh authenticated session
therefore has fresh transport sequence spaces even if the OS reuses its old UDP
port. The client rejects delayed chat/control frames on a previous session's stream.
LOGIN_OK advertises `chat_stream`; new clients reject a missing/mismatched value
instead of silently using incompatible ordering rules. Update client/server together.
Legacy CHAT without message_id is still routed without application delivery guarantees.

## 4. Reliable transport API

```python
transport = ReliableUDP(bind_host, bind_port, key, on_message)
transport.send((host, udp_port), message_dict, stream_id)
transport.send_many((host, udp_port), iterable_of_dicts, stream_id, on_progress=callback)
transport.close()
```

- `on_message(peer_address, stream_uuid, message_dict)` is a callback.
- `on_progress(acknowledged_packet_count)` reports UDP **hop-level** ACKs.
- Each stream delivers its messages in order (not an infinite globally ordered stream).
- Retransmissions are for packets missing ACKs; duplicated packets do not redeliver.
- Producers on the same (peer, stream) are serialized; different streams remain
  independent. An oversized event is rejected before consuming a sequence.
- On retry exhaustion, raise TimeoutError and retain at most one window of
  outstanding frames. The next call retransmits those exact frames with the same
  UUIDs/sequences before its new frames, filling any receiver gap. Neither side
  resets sequence counters. ACK loss may mean the failed call already delivered;
  timeout is an uncertain result. Close discards the transport's pending state.
- DATA is queued in order before sending its ACK, so an ACK send error cannot
  discard accepted data. ACKs must match the expected peer, packet, stream and
  sequence, with a valid AES-GCM credit payload. They prove hop acceptance, not
  final application delivery or verified file storage.
- **Important:** File checksum verification + FILE_RECEIPT is the end-to-end proof,
  not UDP ACK (which only says a packet arrived at the next transport hop).

## 5. Chat and file API

```python
ChatService.build_message(sender, recipient, text)  # -> dict
ChatService.recipients(sender, recipient, online_usernames)  # -> list[str]
FileSender().prepare(path, sender, recipient, display_name=None)
# -> (file_uuid_string, total_udp_packets, generator_of_messages)
receiver = FileReceiver(download_dir)
receiver.process(message_dict)  # -> progress / complete event / None
receiver.close()
```

Default file chunk size = **800 bytes** (`chunk_size` included in FILE_START), intentionally well below the typical
IP MTU once headers and encryption are included. File chunks are transferred
sequentially within a file stream, with an **adaptive window capped at 4 packets**.

## 6. File transfer sequence

The server tracks both participant session tokens and last relay activity until
FILE_RECEIPT. A disconnect, changed session, relay error or 60-second inactivity
removes metadata and sends FILE_ABORT to remaining original sessions. Cleanup
checks/removals share the transfer lock; no network send occurs under that lock.
The receiver serializes writes/abort/timeout/close under its file lock. Only
`.part` files owned by this receiver are removed; verified destinations survive.

```mermaid
sequenceDiagram
    participant A as Sender
    participant S as Server
    participant B as Receiver
    A->>S: FILE_START (UDP DATA, encrypted)
    S-->>A: UDP ACK
    S->>B: FILE_START
    B-->>S: UDP ACK
    loop For each chunk
        A->>S: FILE_CHUNK (sequence/index)
        S-->>A: UDP ACK
        S->>B: FILE_CHUNK
        B-->>S: UDP ACK
    end
    A->>S: FILE_END
    S->>B: FILE_END
    B->>B: SHA-256 verification
    B->>S: FILE_RECEIPT (ok/error)
    S->>A: FILE_RECEIPT (ok/error)
```

## 7. Chat routing sequence

```mermaid
sequenceDiagram
    participant A as Alice
    participant S as Server
    participant B as Bob
    A->>S: CHAT (recipient=bob)
    S-->>A: UDP ACK
    S->>B: CHAT (sender=alice)
    B-->>S: UDP ACK
    B->>B: Accept once by (sender, message_id)
    B->>S: CHAT_ACK (authenticated encrypted DATA)
    S->>A: CHAT_RECEIPT (DELIVERED)
```

### Outbox and reconnection state

The sender assigns a UUID before enqueueing, including file-independent per-chat
status. Only the oldest pending chat is attempted until its application ACKs
complete, preserving order across a reconnect. Failed sends/unknown delivery
remain PENDING. Online retries use 1-8 second intervals, with stable UUID/content.
The server rejects a repeated ID with changed content. Demo mode keeps bounded
5,000-entry RAM routing/inbox caches. Account mode stores sender/ID content hashes
in SQLite and ACKs identical duplicates again without displaying them. Reconnected peers use new UDP sockets
and session-derived stream IDs/sequences; the application message ID survives
that transport change. Reusing an old UDP port is covered by a regression test.

`ClientSession` retains a separate ChatState per username. A successful fresh login
is required before binding/replaying an account's state. Account passwords are not
stored, so network loss/server restart asks for reauthentication. Demo reconnects
with bounded 1/2/4/8-second backoff. Expiration asks for login in either mode.
Explicit logout cancels reconnect and clears disposable events/DOM, but retains
the owner's pending outbox for future login. In account mode, `DurableChatState`
commits outgoing messages before send and incoming messages before application
ACK. `local_chat` is unique by (owner, sender, ID); interrupted SENDING rows reset
to PENDING on reopen. Up to 500 pending messages and the latest 500 displayed
history rows are loaded per owner. SQLite records remain on disk without retention
purging. Demo mode remains RAM-only and loses state when the client process exits.

The account-mode relay persists bodies and separate target ACKs. `SYNC_CHAT`
returns up to four pending messages for the authenticated recipient over verified
TLS; it does not send those offline bodies over UDP. Relay pending entries are
limited to 500 per sender. Delivery receipts require confirmation by every target.
This is idempotent replay with persistent deduplication, not a distributed
exactly-once transaction between independent databases.

### Optional direct peers and channels

Verified TLS `GET_PEERS` issues a capability derived by HMAC-SHA256 from the
server secret and both current session tokens. Direct chat/ACK messages carry a
body proof and session-pair stream ID; the client verifies source endpoint, proof,
stream and stable message content. UDP frames still use the shared AES-GCM key.
An old session pair cannot authorize a new direct message. Direct delivery can
fall back to server relay on retry; persistent deduplication handles both paths.
`JOIN_CHANNEL`/`GET_CHANNELS` manage SQLite membership (eight channels per user,
64 members per channel). A channel chat snapshots its targets like other chat.

### Actual window and congestion behavior

Defaults: MAX_DATAGRAM=1200 bytes, FILE_CHUNK_SIZE=800 bytes, HEADER=42 bytes,
AES-GCM overhead=28 bytes, metadata length=2 bytes, WINDOW_SIZE=4,
ACK_TIMEOUT=0.35 seconds, MAX_RETRIES=10 (initial attempt plus ten retries).
Full chunks carry raw bytes after metadata, not base64. The receiver checks
sequence/chunk index, expected size/count, then SHA-256 before renaming `.part`.

Each (peer, stream) starts at cwnd=1 and one initial credit. The send limit is
`min(WINDOW_SIZE, floor(cwnd), receiver_credit)`. Clean ACKs add 1/cwnd up to four;
network timeouts halve cwnd with floor one, at most once per timeout interval.
The default receive capacity is 16 per stream, accounting for active callbacks,
queued events and out-of-order packets. One slot is reserved for a missing expected
packet. This bounds memory while preserving per-stream ordered delivery.

At zero credit, no new packet ID/sequence is allocated. With no outstanding frame,
the sender repeats its last accepted DATA as a credit probe and waits for its ACK;
the receiver deduplicates it and reports current capacity. Outstanding retries at
zero credit do not consume network retry budget or reduce cwnd. A separate
FLOW_TIMEOUT=10 seconds bounds this waiting; `flow_waits` and network `timeouts`
are separate metrics. A fresh later send can recover retained uncertain frames.
Run `python -m scripts.flow_demo` for actual ACK, timeout, cwnd and credit values.
This is AIMD, with no bandwidth/RTT estimator, adaptive pacing, BBR or CUBIC.

### Local HTTP(S) adapter

The adapter parses one request per connection, rejects duplicate headers, enforces
header/body limits and constructs explicit Content-Length responses. Up to 32
HTTP workers run concurrently. Account APIs require HTTPS and a random Secure,
HttpOnly, SameSite=Strict cookie named `collab_session_<UI port>`; ports need
different cookie names because browser cookies are not port-isolated. Logout
revokes the token and clears visible history. Client-side generation guards reject
stale poll responses after logout. Previously authenticated disconnected profiles
can enqueue chat to known contacts; file sending requires a live connection.

## 8. Assignment scope

The implementation uses TCP/TLS for control/offline synchronization and reliable UDP for live chat/files;
the browser UI uses a raw-socket local HTTP(S) adapter with client-side JavaScript.
The supplied lecturer clarification permits standard TCP and a tested, explainable
congestion mechanism such as AIMD; StreApRous, raw TCP/IP and separate P2P/channels
are optional. No reference framework or additional TCP encryption layer is used.
