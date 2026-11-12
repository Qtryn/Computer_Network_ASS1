# Final testing and pre-report audit — 2026-11-13

Final local verification is complete. Automated and recorded browser checks pass;
submission sign-off remains conditional on the specification questions and final
report/package. This is an audit record, not the Technical Explanation Report PDF.

## A. Repository baseline

- Work stayed on `main`, initially clean at
  `80c6f250711793f17df19bf378ac9f744074c088`. No branch, merge, reset, commit or push
  was performed during verification. The user separately authorized publication
  of the completed audit afterward.
- Python 3.14.5; Node v24.15.0. Application dependency cryptography 46.0.7
  (`>=43,<47`), with cffi 2.1.1 / pycparser 3.12 installed transitively.
- Initial baseline 62 Python tests passed. Three meaningful socket/process audit
  tests were added; final suite contains 65 tests.
- Read the supplied five-page Assignment Specification, SHA-256
  `88c2a103062de07212f1eac22907da0d4e3a750cf522a08ee91728a792aae3d4`.
  The 41-file app/scripts/tests import audit found only cryptography external.
  pypdf under gitignored downloads/audit-tools was a PDF-reading tool only.

## B. Final test results

| Test | Result | Evidence | Notes |
|---|---|---|---|
| Full Python rerun | **PASS: 65/65**, 43.045s suite | evidence/final-audit-2026-11-13/unittest.txt | Exit 0, no skips/failures; 43.584s including startup |
| Smoke | **PASS**, 1.044s | Same directory, smoke.txt | Real TCP/UDP login/chat/file/hash/receipt/logout |
| Load | **PASS: 20 clients**, 2.659s | Same directory, load.txt | Localhost |
| JS UI logic | **PASS**, 0.213s | Same directory, ui.txt | DOM double, not browser evidence |
| Expanded concurrency | **PASS: 2/10/20 clients** | tests/test_final_audit.py; prior audit logs | Concurrent global/private chat, 1/5/10 files, SHA-256 and lifecycle cleanup |
| HTTPS/TLS account integration | **PASS** | Full-suite tests + browser-account-e2e.md | Register/persistence/validation, password throttling, duplicate login, hostname/untrusted-CA rejection |
| Real trusted Chrome accounts | **PASS, recorded scope** | evidence/final-audit-2026-11-12/browser-account-e2e.md | Register/login/logout/relogin, storage, Unicode file, restart/reauthentication, ordered outbox and identity isolation |
| Remaining Chrome file/chat cases | **PASS** | evidence/final-audit-2026-11-13/browser-file-chat.json and README | Account broadcast once, empty/binary hashes, chat visible at 35% of 2 MiB receive |
| Transport/resilience | **PASS** | Full-suite transport/lossy/registration tests | Loss, duplicates, reorder, retry exhaustion/recovery, app ACK loss, revoked/stale sessions and file cleanup |
| Actual idle timeout | **PASS**, 12.093s observation | prior audit timeout-detection.txt | Default 12s setting; another heartbeat client stayed online |
| Wireshark | **PASS**, actual capture retained | docs/wireshark_demo.md; capture-analysis.json | New audit capture: 389 frames, 0 interface drops; DATA retry at 109/120 and ACK 121 |
| Two-machine LAN | **NOT TESTED** | No independent second host available | Loopback is not relabeled as LAN |

The [latest evidence index](evidence/final-audit-2026-11-13/README.md) links the
fresh logs and earlier artifacts without overwriting provenance. No password,
authentication token, AES key or TLS private key is exported in the audit results.

## C. Bugs found and fixed

No new reproducible application defect was found, so application source and
requirements were left unchanged. No cosmetic refactor or feature expansion was
performed. Existing dropdown/progress-buffer fixes in 80c6f25 remained verified.

Three tests were added in `tests/test_final_audit.py`:

1. Concurrent 2/10/20-user login/chat/file/logout and SHA-256; empty transfer
   metadata/parts/registry/connections, closed client sockets and stopped threads.
2. Changed-content reuse of a chat UUID rejected by server/receiver, with one
   original received copy.
3. Real local client process termination/restart confirms pending RAM outbox loss.

All three passed alone and in two full 65-test runs. The browser loss harness was
test-only, and the final running server has no fault hook. Test-only fixture and
native-input recovery issues were not reported as application bugs.

## D. Remaining limitations

- **CRITICAL for final sign-off:** the PDF names BBR/CUBIC in techniques, while
  this UDP transport has only a fixed window. Resolve required scope with the
  lecturer or implement the specifically agreed requirement before claiming
  compliance. No BBR/CUBIC, RTT/bandwidth estimator, adaptive window or pacing
  exists; a simple AIMD proposal would still not be BBR/CUBIC.
- **IMPORTANT:** confirm TCP-control/UDP-data wording, the CLI/GUI vs HTTP wording,
  RAM-only offline scope, five-person group vs Individual/Pair, and official
  deadline. The PDF's “Sunday, November 17, 2026” date is a Tuesday. Two-host LAN
  remains untested; the PDF permits localhost or local IP addressing.
- **OPTIONAL unless confirmed required:** durable outbox/database, file resume,
  prolonged/very-large-file benchmarks and larger client counts. No such feature
  was silently added. Current short tests do not prove absence of all possible
  long-term resource growth or races.

Offline behavior is explicit: pending queues survive server restart/logout only
inside the same local process and resume only for the correct authenticated
owner. Closing that process loses its outbox/dedup state. UI sending is disabled
while disconnected; offline composition is not implemented.

## E. Ten-milestone compliance

| Milestone | Status | Implementation / test evidence | Remaining limitation / action |
|---|---|---|---|
| 1. Protocol and state design | **PARTIAL** | common/protocol.py; docs/protocol.md and architecture.md; framing/budget tests | Cannot establish design preceded coding; retain design history if available |
| 2. TCP handshake | **PASS** | server._serve_control, client._read_control_line; fragmented/coalesced tests and capture | Localhost scope |
| 3. Authentication and registry | **PASS** | PasswordAccounts, UserRegistry; TLS/socket and real browser account checks | Basic local accounts/shared-key model, not production identity |
| 4. Concurrency | **PASS** | Threaded server and locked state; real 2/10/20-client cases and cleanup | Short runs; no LAN/long-term claim |
| 5. Time-sensitive streaming | **PARTIAL** | _route_chat, per-stream UDP workers; lossy concurrent chat/file, Chrome chat at 35% receive | BBR/CUBIC technique requirement unresolved |
| 6. Reliable UDP file transfer | **PASS** | FileSender/FileReceiver/ReliableUDP; empty/text/binary/Unicode SHA-256, retry/reassembly and receipts | No file resume; 2 MiB browser sample is not arbitrary-size proof |
| 7. Resilience | **PASS** | ClientSession, ChatState, close/cleanup; real restart/replay/isolation plus fault tests | RAM-only recovery scope documented |
| 8. Encryption | **PASS** | CryptoBox AES-GCM and verified TLS; tamper/CA/hostname tests, trusted Chrome | Shared demo AES key; transport ACK alone is not security/delivery proof |
| 9. HTTP UI + JavaScript | **PASS** | raw-socket local_web/index.html; real demo and trusted account browser checks | Windows localhost tested; no framework |
| 10. Tests and code quality | **PASS** | 65 tests, smoke/load/JS, 41-file import audit, real captures and browser flows | Report/package are separate deliverables; no predicted score claimed |

Detailed source/test mapping remains in [rubric_checklist.md](rubric_checklist.md).

## F. Report readiness

- **READY TO WRITE REPORT: YES.** Existing architecture, packet table, state/chat/
  file diagrams and audited results can be reused. No complete report PDF was
  written in this task, as requested.
- **READY TO SUBMIT: NO.** Resolve congestion/specification acceptance, then finish
  and review the Technical Explanation Report PDF and submission package.
- **NOT READY:** unconditional submission sign-off or a claim of 10/10. Available
  local tests are complete; the trusted-browser blocker has been resolved.

## G. Exact verification commands

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.smoke_test
.\.venv\Scripts\python.exe -m scripts.load_test
node scripts/test_ui.cjs
git diff --check
git status --short --branch
```

For capture commands, filters, hashes and frame numbers, use the existing
[Wireshark guide](wireshark_demo.md). Keep the real demo running concurrently with
Npcap; do not generate replacement PCAP packets or disable certificate validation.

## H. Git changes

- Modified README and existing test-plan/rubric/integration/Wireshark/evidence
  documentation to reflect actual results and artifact provenance.
- Added this final audit, two dated evidence directories and
  `tests/test_final_audit.py` (three tests). No files removed; no prior test changed.
- Application source/requirements unchanged; no new application dependencies.
- Verification completion state: `main`, audit tests/docs/evidence modified or
  untracked, `git diff --check` clean. Commit/push of the completed audit was
  subsequently authorized by the user; the source SHA above identifies the
  application version actually tested.
