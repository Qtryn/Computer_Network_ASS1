# Assignment rubric: 10 requirements × 1 point

**Important:** The following is a truthful development status of the initial
scaffold, NOT an official or predicted grade.

| Step | Requirement in handout | Current status | Evidence / remaining work |
|---|---|---|---|
| 1 | Packet/message specification + state diagrams before coding | **Partial** | `docs/protocol.md` has wire format and sequence diagrams; finalize state diagrams/teacher-approved spec |
| 2 | Basic TCP handshake + ACK | **Demo works** | TCP LOGIN → LOGIN_OK in localhost smoke test; verify with instructor if separate handshake is expected |
| 3 | Authentication, IP/port/user registry | **Basic demo works** | Username + random session token and IP/UDP port; no password authentication |
| 4 | 10–20 concurrent clients/Async I/O | **Local 20-client test passed; LAN pending** | Threaded TCP and per-stream UDP; `scripts/load_test.py` runs 20 localhost clients |
| 5 | Time-sensitive streaming, broadcast and unicast | **Demo works; verify HoL/congestion requirements** | Chat routing and per-stream workers; fixed window, no BBR/CUBIC |
| 6 | Reliable UDP file chunking and reassembly | **Demo works; stress pending** | FileSender/FileReceiver + UDP ACK/retry; binary + empty unit tests + localhost smoke |
| 7 | Error handling and network resilience | **Partial** | Timeouts, retries, logout and basic malformed-packet handling; test crash/LAN outage/reconnect |
| 8 | Encrypt payload before sending | **Demo works** | AES-GCM for UDP DATA, tamper unit test; no negotiated key exchange |
| 9 | HTTP UI with client-side JavaScript | **Demo works; interpretation pending** | Browser UI via Python localhost raw HTTP sockets + JS; confirm HTTP/CLI contradiction with teacher |
| 10 | Quality, multi-client local tests | **Partial** | 13 unit tests + 2-client smoke + 20-client localhost script; add LAN evidence and final report |

## Key discrepancies that the team must not silently ignore

1. The handout mentions both TCP (handshake and some transport notes) and UDP
   streaming, with file-transfer-over-UDP expressly required in Step 6.
2. Design section permits CLI/GUI, but rubric Step 9 names HTTP UI + client-side JS.
3. BBR/CUBIC are mentioned in techniques despite no dedicated scoring row.
4. The original handout says *Individual / Pair Project*; allocation says 5.
5. Proposed deadline day/date appear inconsistent; check LMS/teacher.

**Claiming full compliance before resolving the above would be inaccurate.**
