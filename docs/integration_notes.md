# Member 4 integration and confirmed requirements

## Branch/history

- Working branch: `integration/member4-and-fixes`, created from freshly fetched
  `origin/main` at `e5ee454`. The working tree was clean before starting.
- Source UI/evidence branch: `origin/feature/member4-ui` at `7319f68`.
- `git merge-base --is-ancestor origin/tv1-server-core origin/main` returned 0;
  that server branch is already merged and was not merged again.
- Selection was performed with reviewed diffs and targeted patches. There was
  no blind merge, conflict-marker resolution or history rewrite. The user later
  authorized a local fast-forward main merge and then a push through `80c6f25`.
  The later pre-report audit initially left its tests/docs/evidence uncommitted
  and unpushed, as requested; the user then separately authorized publication.

## Selected and excluded changes

Selected Member 4's separate progress labels for receiving, server ACK and final
recipient SHA-256 confirmation; connection indicators and disabled controls;
outgoing-chat dedup intent; login/logout regression scenarios; 13 Windows and
3 Ubuntu screenshots unchanged, with provenance in `evidence/README.md`.

Kept **ClientSession** and adapted useful behavior to it. Did not import
LocalUIState, the username-only account flow, the old client/control reader,
or the handler that indexes a dict returned by send_chat. send_chat still returns
None; HTTP returns `{ok:true}` and polling renders the single outgoing event.
Preserved TLS/HTTPS, password verification, token cleanup, ReliableUDP recovery,
file cleanup/SHA-256 and session event handling on main. New session-scoped stream
IDs extend ordering safely without changing the UDP frame layout.

## Modified source/test files

| File | Reason |
|---|---|
| app/client.py | TLS registration helper, stable-ID outbox/app ACKs, fresh-session stream checks |
| app/common/protocol.py | Hash-derived session stream helper, no token-byte exposure |
| app/features/chat.py | Include message IDs/targets in datagram-budget validation |
| app/features/outbox.py | Small private per-account RAM queue and bounded receiver dedup cache |
| app/server/auth.py | Validated, locked PBKDF2 registration with atomic JSON persistence |
| app/server/registry.py | Derive the session's chat stream |
| app/server/server.py | TLS REGISTER, routing/ACK records, session stream validation |
| app/run_server.py | Start account mode with empty/missing store; persist new registrations |
| app/run_client.py | Wire registration, private ChatState and demo reconnect into ClientSession |
| app/web/local_web.py | Keep ClientSession, registration endpoint, backoff and reauth policy |
| app/web/static/index.html | Member 4 progress/status, Register, pending/delivered dedup display |
| tests/test_client.py | Adapted Member 4 event fixtures including running state |
| tests/test_local_web.py | Adapted Member 4 HTTP/login/logout and None-return chat regression |
| tests/test_registration_outbox.py | Registration, restart, order, dedup, identity, reused-port and Unicode tests |
| scripts/test_ui.cjs | Registration/password clearing, progress, outgoing dedup and status tests |
| scripts/wireshark_demo.py | Real synthetic TLS/UDP traffic with one lost ACK and server restart |

README/protocol/test-plan/rubric/getting-started/architecture docs reflect the
actual behavior; `wireshark_demo.md` records real packet observations. No runtime
dependency was added: import audit found only cryptography outside the stdlib.

## Explicit behavior and limits

- DELIVERED means all intended recipient applications acknowledged, not transport
  ACK, server acceptance, human reading or durable storage. Broadcast targets are
  fixed at enqueue. The oldest pending message completes before the next is sent.
- Account mode never saves a password for background login. Unexpected loss asks
  for credentials again; the successful fresh login resumes that account's RAM
  outbox. Demo mode alone automatically reconnects with 1/2/4/8-second backoff.
  Expiration requires login in either mode. Explicit logout cancels reconnect.
- Logout clears session events and browser history but retains owner-only pending
  entries in the local process. Another authenticated account cannot see/send them.
  No outbox or receiver dedup state survives closing the local application.
- Outboxes are bounded to 500 pending messages/account; receiver dedup and server
  routing caches to 5,000 entries. No durable exactly-once guarantee is claimed.
- No server-side offline history sync, file resume, BBR or CUBIC was added.
  Confirm whether offline synchronization must survive app restart, and which
  exact congestion algorithm the instructor expects before expanding scope.

## Evidence boundary

Final checks on 2026-11-12:

```text
python -m unittest discover -s tests -v   62 passed, 0 failed (baseline: 41)
python -m scripts.smoke_test             PASS
python -m scripts.load_test              PASS, 20 connected clients
node scripts/test_ui.cjs                 PASS, DOM double only
python -m scripts.wireshark_demo          PASS, real TLS/UDP demo
git diff --check                         PASS
```

Static import audit covered 40 Python files: cryptography is the only external
package. The original tests/test_packet_budget.py, ReliableUDP, FileReceiver and
CryptoBox implementations were preserved; added metadata budget tests live in
the new registration/outbox test file.

The final capture contains 373 actual loopback frames (TCP 9100 / UDP 9101),
including TLS, DATA/ACK, repeated UUID/ciphertext after lost ACK, file transfer
and fresh sessions after restart. See `wireshark_demo.md` for frame numbers/hash.

After the initial URL-confidence block, a real Windows Chrome retry verified
demo-mode login, private/broadcast chat, native file chooser, Unicode/empty/binary
SHA-256 receipts, chat during transfer, logout/relogin and server restart. It found
and fixed per-poll dropdown rebuilding and progress events evicting chat from the
bounded event buffer. Added regressions passed with the full suite. Details and
the original demo browser scope: [evidence/browser-e2e.md](evidence/browser-e2e.md).
Imported Member 4 screenshots remain historical and are not final-run evidence.

The later pre-report audit reran 62 baseline tests, added three real-socket/process
audit tests and passed all 65. A separate trusted HTTPS Chrome follow-up passed
account registration/login/throttling/logout, Unicode file, server restart,
ordered pending replay and cross-account isolation. Browser storage was empty on
both origins. See `evidence/final-audit-2026-11-12/README.md` and its browser record.
No new application source defect or source change was required by that audit.

Final verification on 2026-11-13 passed a fresh 65-test/smoke/load/UI run and the
remaining real HTTPS account broadcast, empty/binary file and chat-during-transfer
scenarios. `docs/final_audit.md` is the final audit summary; dated logs and prior
capture/browser provenance remain under `docs/evidence/`. After verification,
the user authorized committing and pushing the audit. LAN and BBR/CUBIC are not
claimed as complete.
