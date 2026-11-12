# Assignment rubric: 10 requirements × 1 point

Verified on 2026-11-12. This is an evidence checklist, not a predicted grade.

| Step | Requirement in handout | Current status | Evidence / remaining work |
|---|---|---|---|
| 1 | Packet/message specification + state diagrams before coding | **PARTIAL** | Wire format, sequence and lifecycle diagrams in `docs/protocol.md`; cannot establish that design preceded coding |
| 2 | Basic TCP handshake + ACK | **PASS** | Real HELLO/HELLO_OK and LOGIN/LOGIN_OK, including fragmented/coalesced control tests |
| 3 | Authentication, IP/port/user registry | **PASS** | HTTPS local login + verified server TLS, PBKDF2 passwords, invalid/duplicate login, expiry and revoked-token tests |
| 4 | 10–20 concurrent clients/Async I/O | **PASS** | Threaded server; concurrent 20-login test and 20 connected clients in load script, localhost only |
| 5 | Time-sensitive streaming, broadcast and unicast | **PARTIAL** | Private/broadcast routing and chat during lossy file transfer pass; BBR/CUBIC is absent and its required scope needs confirmation |
| 6 | Reliable UDP file chunking and reassembly | **PASS** | Empty/text/binary hashes, 60 KiB lossy transfer, ordering/duplicates/retries and receiver receipts verified |
| 7 | Error handling and network resilience | **PASS** | Real TCP loss, malformed/oversized data, UDP exhaustion/recovery, sender/receiver logout, timeout cleanup; localhost/fault injection scope |
| 8 | Encrypt payload before sending | **PASS** | AES-GCM tamper tests, trusted/untrusted/hostname TLS tests; raw sockets plus standard crypto library |
| 9 | HTTP UI with client-side JavaScript | **PARTIAL** | Raw HTTP(S) endpoints and actual JS with DOM double tested; browser automation failed to initialize, manual rendering/trust checks pending |
| 10 | Quality, multi-client local tests | **PARTIAL** | Unit/integration, smoke, 20-client load and JS checks pass; actual browser/multiple-terminal screenshots, LAN evidence and final submission report pending |

## Key discrepancies that the team must not silently ignore

1. The handout mentions both TCP (handshake and some transport notes) and UDP
   streaming, with file-transfer-over-UDP expressly required in Step 6.
2. Design section permits CLI/GUI, but rubric Step 9 names HTTP UI + client-side JS.
3. BBR/CUBIC are mentioned in techniques despite no dedicated scoring row.
4. The original handout says *Individual / Pair Project*; allocation says 5.
5. Proposed deadline day/date appear inconsistent; check LMS/teacher.

**Claiming full compliance before resolving the above would be inaccurate.**
