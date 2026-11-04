# Protocol specification (version 1)

**Do not modify this contract without team review.** Member 1 + Member 2 own protocol updates.

## 1. TCP control (one JSON object + `\n` per message)

Client -> server:

```json
{"type":"LOGIN","username":"alice","udp_port":54321}
```

Server -> client:

```json
{"type":"LOGIN_OK","token":"<random-session-token>","users":["alice","bob"],"version":2,"udp_port":9101}
```

Other control messages: `PING`, `LOGOUT`, `ERROR`. TCP uses newline-delimited
JSON framing because `recv()` alone does not preserve message boundaries.
One active session per username; account passwords are **not** implemented.

## 2. UDP frame bytes

| Field | Bytes | Meaning |
|---|---:|---|
| Magic `COLB` | 4 | Protocol recognition |
| Version | 1 | `1` |
| Kind | 1 | `1=DATA`, `2=ACK` |
| Sequence | 4 | Big endian unsigned integer, starts at 0 per (peer,stream) |
| Packet ID | 16 | UUID; ACK references exactly this packet |
| Stream ID | 16 | UUID; chat uses constant `...0001`; file uses file UUID |
| Payload | variable | For DATA: 12-byte nonce + AES-GCM ciphertext (includes 16-byte authentication tag) |

Header size: **42 bytes**. Maximum UDP datagram: **1200 bytes**.
ACK datagram contains only the 42-byte header and is NOT encrypted; it has no
application payload. The AES-GCM associated authenticated data (AAD) is the header.

The encrypted application message contains:

```
[2-byte metadata JSON length][UTF-8 JSON metadata][optional raw file bytes]
```

Only file chunks have raw binary data; no base64 expansion inside messages.
All UDP DATA payloads are encrypted and authenticated by the shared AES-GCM key.
A new 12-byte random nonce is generated per DATA frame. Reusing a nonce with
same key is dangerous; do not change this design without Member 5 review.

## 3. UDP application message types

| Type | Required fields | Meaning |
|---|---|---|
| `USERS` | `users, version` | Server updates online usernames (monotonic version avoids stale updates) |
| `CHAT` | `sender, recipient, text` | Broadcast if `recipient="*"`, otherwise private |
| `FILE_START` | `file_id, sender, recipient, name, size, total_chunks, chunk_size, sha256` | Announce file and expected hash |
| `FILE_CHUNK` | `file_id, sender, recipient, index, data` | Binary file chunk, starts at index 0 |
| `FILE_END` | `file_id, sender, recipient` | File transmission finished |
| `FILE_RECEIPT` | `file_id, sender, status, message` | Receiver confirms complete hash check or error |
| `ERROR` | `message` | Application error response |

Client -> server messages add `token` containing the authenticated session token.
Server -> client messages intentionally omit token. `data` is a Python `bytes`
field that becomes the raw byte suffix of the encrypted application message.
A file stream uses the file's `file_id` as its Stream ID.

## 4. Transport API (Member 2, already callable)

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
- **Important:** File checksum verification + FILE_RECEIPT is the end-to-end proof,
  not UDP ACK (which only says a packet arrived at the next transport hop).

## 5. Member 3 API (already implemented)

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
sequentially within a file stream, with a **fixed window of 4 UDP packets**.

## 6. File transfer sequence

```mermaid
sequenceDiagram
    participant A as Sender (Member 3)
    participant S as Server (Member 1 + Member 2)
    participant B as Receiver (Member 3)
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
```

## 8. Pending teacher confirmation

1. Does the TCP handshake + UDP streaming split satisfy both TCP and UDP wording?
2. Is the local HTTP + client-side JS solution acceptable for Step 9?
3. Is a fixed sliding window sufficient, or must congestion control actually
   implement BBR/CUBIC? **Current version does not implement BBR/CUBIC.**
4. Is the five-person group and revised deadline confirmed?
