# Assignment rubric: 10 requirements × 1 point

Pre-report audit on 2026-11-12, clean baseline `80c6f25` on main. This is an
evidence checklist, not a predicted grade. PASS refers to the stated localhost
scope; it does not mean production readiness or a verified lecturer waiver.

Final verification completed 2026-11-13: fresh 65-test/smoke/load/UI rerun and
remaining HTTPS browser file/chat scenarios passed. See [final_audit.md](final_audit.md).

| Step | Requirement | Status | Implementation | Tests / actual evidence | Limitation / minimal next action |
|---|---|---|---|---|---|
| 1 | Packet design and state diagrams before coding | **PARTIAL** | `common/protocol.py`; `docs/protocol.md`, `architecture.md` | Protocol framing/budget tests, existing chat/file/state diagrams | Cannot prove design preceded coding; retain design history if available |
| 2 | Basic TCP handshake and acknowledgment | **PASS** | `server.py::_serve_control`, `client.py::_read_control_line` | `test_split_hello_and_coalesced_requests`, smoke; new capture SYN/SYN-ACK and TLS | Localhost; keep TCP-control/UDP-data split explicit |
| 3 | Authentication and IP/port registry | **PASS** | `PasswordAccounts.register/verify`, `UserRegistry.login/authenticate` | HTTPS registration persistence, TLS password/hostname/untrusted-CA, duplicate/throttling/expiry tests in final 65-test log | Browser account validation is tracked separately under 9; no credential caching |
| 4 | Concurrent connecting/disconnecting clients | **PASS** | Threaded accept/control workers, locked registry | `test_concurrent_chat_files_logout_and_resource_cleanup`: 2/10/20 concurrent users, chats and 1/5/10 files; socket/thread/registry cleanup | Short localhost runs only; no long-duration or two-host LAN claim |
| 5 | Async time-sensitive routing, broadcast/unicast | **PARTIAL** | `_route_chat`, ReliableUDP per-stream workers | Concurrent broadcast/private tests, lossy chat during file test, prior real Chrome chat at 76% file progress | BBR/CUBIC listed in techniques is NOT IMPLEMENTED; get lecturer scope/waiver before submission |
| 6 | Reliable UDP file chunking/reassembly | **PASS** | `FileSender.prepare`, `FileReceiver.process`, `ReliableUDP.send_many` | Empty/text/binary/Unicode SHA-256, lossy/reorder/duplicate/exhaustion recovery tests; new 43-sequence captured file stream | 800-byte chunks, fixed window 4; no resume or arbitrary-size benchmark |
| 7 | Network resilience and errors | **PASS** | `CollaborationClient.close`, `ClientSession`, `ChatState`, transfer cleanup | Restart/ordered stable-ID replay, lost application ACK, wrong-account isolation, changed-content ID rejection; actual 12s idle timeout | RAM-only outbox lost on local process restart (new subprocess test confirms); offline UI composition disabled |
| 8 | Standard encrypted payloads | **PASS** | `CryptoBox` AES-GCM, verified Python TLS contexts | Tamper/header/wrong-key tests, untrusted/hostname TLS rejection; capture has ciphertext and no exported decryption secrets | Shared demo AES key; transport ACK is unencrypted and is not application delivery proof |
| 9 | HTTP UI and client-side JavaScript | **PASS** | `local_web.py::handle_request`, `static/index.html` | Real Chrome demo plus trusted HTTPS register/login/lockout/logout/relogin, broadcast, empty/text/binary files, concurrent chat, restart/outbox replay; both origins' Local/Session Storage empty | Local Windows scope; see dated browser records; DOM-double results remain separate |
| 10 | Testing and code quality | **PASS** | Raw sockets, stdlib plus cryptography; 41-file import audit | Fresh 62-test baseline; final 65 pass, smoke/load/UI pass, new 389-frame real capture | Evidence is bounded local testing, not proof of no possible races; report PDF and submission packaging remain separate deliverables |

## Key discrepancies that the team must not silently ignore

1. The handout mentions both TCP (handshake and some transport notes) and UDP
   streaming, with file-transfer-over-UDP expressly required in Step 6.
2. Design section permits CLI/GUI, but rubric Step 9 names HTTP UI + client-side JS.
3. BBR/CUBIC are mentioned in techniques despite no dedicated scoring row.
4. The original handout says *Individual / Pair Project*; allocation says 5.
5. Proposed deadline day/date appear inconsistent; check LMS/teacher.

The PDF actually says Sunday, November 17, 2026; that calendar date is Tuesday.
Its environment requirement permits localhost **or** local IP addressing, so
unavailable two-host LAN evidence is NOT TESTED, not an invented local test pass.
The PDF does not define persistent offline synchronization. Current RAM-only
behavior must be stated; do not add a database without confirmed scope.

See `evidence/final-audit-2026-11-12/` for fresh logs, capture and readiness notes.

**Claiming full compliance before resolving the above would be inaccurate.**
