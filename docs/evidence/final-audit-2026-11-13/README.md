# Final verification — 2026-11-13

Continuation of the [2026-11-12 audit](../final-audit-2026-11-12/README.md).
Application source remains `80c6f250711793f17df19bf378ac9f744074c088`; no new
application defect or production source/dependency change was required.

## Fresh automated checks

| Check | Result | Actual duration | Evidence |
|---|---|---:|---|
| Python unittest | 65 passed, 0 failures/skips | 43.045s suite / 43.584s command | unittest.txt |
| Smoke | PASS | 1.044s command | smoke.txt |
| Load | PASS, 20 connected clients | 2.659s command | load.txt |
| JavaScript | PASS, DOM double | 0.213s command | ui.txt |

`verification-summary.json` records exit 0 for each command. Durations are single
local observations, not throughput or latency guarantees. The three added tests
remain in `tests/test_final_audit.py`; prior tests were not changed or weakened.

## Remaining real HTTPS browser scenarios completed

The audit listeners had stopped since the previous session and were restarted
on the same account server TCP/UDP 19000/19001 and HTTPS UI ports 18411/18412.
The browser access host was unavailable, so native Chrome was used after the user
opened the exact application tabs. The first native attempt was stopped by URL
confidence enforcement; the completed run below occurred after that handoff.
No warning was bypassed. Existing test_alice/test_bob accounts were logged in
through the actual browser, using the already trusted certificate.

| Action in Chrome | Actual result |
|---|---|
| Alice → Everyone: `HTTPS final broadcast 2026-11-13` | Alice showed DELIVERED; Bob displayed exactly one incoming row |
| Bob selected Alice, native chooser selected empty.txt | Sender showed recipient SHA-256 receipt; Alice displayed completed file; 0-byte hash matched source |
| Native chooser selected binary.bin, 2 MiB | Sender's server ACK label was separate from recipient receipt; receiver finished at 100% with SHA-256 verified |
| Bob sent `HTTPS chat during 2 MiB binary 2026-11-13` while file was active | Alice displayed that chat while receiving at **35%**, before completion; Bob showed DELIVERED; receiver had exactly one chat row |

Complementary read-only HTTPS state checks verified the broadcast/chat row counts
and application file receipt. Independent disk SHA-256 matched source fixtures:

| Received file | Bytes | SHA-256 |
|---|---:|---|
| empty.txt | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| binary.bin | 2097152 | `1e075c8d478ad21844e33e830a695ef03a4d2488b69ee275bd8947618bb1be1e` |

See `browser-file-chat.json`. The Unicode 62-byte text upload was already verified
in the [trusted account browser run](../final-audit-2026-11-12/browser-account-e2e.md),
so account browser evidence now covers empty/text/binary and concurrent chat.
These results come from browser actions plus observed UI, not HTTP-only tests.
No new screenshot files or packet capture were exported in this continuation.

## Final consistency and scope

`final-status.json` confirms Python 3.14.5, cryptography 46.0.7, trusted Windows
root certificate, unchanged application/requirements, only config/.gitkeep
tracked, and unchanged SHA-256 of both historical real captures. Neither pcapng
contains a Decryption Secrets Block. The 389-frame capture and its 0-drop/TShark
analysis remain valid evidence from the earlier actual socket demo, not this
browser session. Passwords/tokens/private keys are absent from the new results.

Offline UI composition is **not supported**: recipient options list online peers
and sending is disabled while disconnected. Pending recovery refers to messages
already queued before uncertain/failed delivery. That real-browser case, same-ID
ordered restart replay and other-account isolation passed in the prior trusted
run. RAM-only outbox loss on process restart is confirmed by a real subprocess
test; no durable/offline history claim is made.

All available local test work is complete. Two independent LAN hosts remain
**NOT TESTED**; adaptive congestion control/BBR/CUBIC remain **NOT IMPLEMENTED**.
No attempt was made to change their scope or hide those gaps. The final audit
and submission-readiness decision are in [final_audit.md](../../final_audit.md).
At verification completion, changes were left uncommitted/unpushed and both
account UIs running. The user subsequently authorized publication of this audit.
