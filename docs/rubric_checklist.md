# Assignment rubric: 10 requirements × 1 point

Verified on 2026-11-12. This is an evidence checklist, not a predicted grade.

| Step | Requirement in handout | Current status | Evidence / remaining work |
|---|---|---|---|
| 1 | Packet/message specification + state diagrams before coding | **PARTIAL** | Wire format, sequence and lifecycle diagrams in `docs/protocol.md`; cannot establish that design preceded coding |
| 2 | Basic TCP handshake + ACK | **PASS** | Real HELLO/HELLO_OK and LOGIN/LOGIN_OK, including fragmented/coalesced control tests |
| 3 | Authentication, IP/port/user registry | **PASS** | HTTPS/TLS login and registration, PBKDF2/atomic persistent accounts, duplicate/expiry/token tests |
| 4 | 10–20 concurrent clients/Async I/O | **PASS** | Threaded server; concurrent 20-login test and 20 connected clients in load script, localhost only |
| 5 | Time-sensitive streaming, broadcast and unicast | **PARTIAL** | Private/broadcast routing and chat during lossy file transfer pass; BBR/CUBIC is absent and its required scope needs confirmation |
| 6 | Reliable UDP file chunking and reassembly | **PASS** | Empty/text/binary hashes, 60 KiB lossy transfer, ordering/duplicates/retries and receiver receipts verified |
| 7 | Error handling and network resilience | **PASS** | TCP loss/restart, ordered outbox replay, application ACK/dedup, reused UDP port, session isolation and original cleanup tests; local scope |
| 8 | Encrypt payload before sending | **PASS** | AES-GCM tamper tests, trusted/untrusted/hostname TLS tests; raw sockets plus standard crypto library |
| 9 | HTTP UI with client-side JavaScript | **PARTIAL** | ClientSession integration, real Chrome demo login/chat/files/logout/reconnect passed; account/HTTPS browser checks remain manual; see evidence/browser-e2e.md |
| 10 | Quality, multi-client local tests | **PARTIAL** | 62 Python tests, smoke, 20 clients, real Chrome demo checks and 373-frame Npcap capture; historical images retain provenance; LAN/final report pending |

## Key discrepancies that the team must not silently ignore

1. The handout mentions both TCP (handshake and some transport notes) and UDP
   streaming, with file-transfer-over-UDP expressly required in Step 6.
2. Design section permits CLI/GUI, but rubric Step 9 names HTTP UI + client-side JS.
3. BBR/CUBIC are mentioned in techniques despite no dedicated scoring row.
4. The original handout says *Individual / Pair Project*; allocation says 5.
5. Proposed deadline day/date appear inconsistent; check LMS/teacher.

**Claiming full compliance before resolving the above would be inaccurate.**
