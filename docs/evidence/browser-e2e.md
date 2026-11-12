# Integrated browser verification — 2026-11-12

This is the earlier demo-mode record. Trusted HTTPS account verification was
subsequently completed and is recorded separately in
[browser-account-e2e.md](final-audit-2026-11-12/browser-account-e2e.md), preserving
the scope and provenance of the original observations below.

Observed in real Windows Chrome using Computer Use on the integration branch
(`889ae10` plus the fixes committed with this record). This is a written record
of actual browser observations; no new screenshot files are included. The older
Member 4 images keep their historical provenance.

Setup: raw-socket demo server TCP 9100 / UDP 9101, local HTTP UIs
`http://127.0.0.1:18011/` (browser_alice) and
`http://127.0.0.1:18012/` (browser_bob). Both pages were opened and operated in
Chrome. The localhost connection refusal was resolved by starting the listeners
on these exact ports.

| Scenario | Observed result |
|---|---|
| Demo login / roster | Both users Connected; both names online; send controls enabled |
| Private Bob → Alice | One outgoing row marked DELIVERED and one incoming row |
| Broadcast Alice → everyone | One outgoing DELIVERED row; Bob received it once |
| Recipient selection across polls | Alice selection stayed selected; open dropdown remained usable after fix |
| Native file chooser | Selected Unicode text, empty file and 2 MiB binary from local synthetic fixtures |
| File receipts | Sender showed server chunk ACK separately from recipient SHA-256 receipt; receiver showed verified file path |
| Chat during binary transfer | After fix, Alice displayed `E2E retained chat during binary 04` while receiving at 76%, before completion; chat remained after completion |
| Logout / relogin on same page | Feed emptied, selection reset to Everyone, progress 0%, chat/file disabled; Bob stayed Connected and roster excluded Alice; relogin showed only the new login event |
| Completed files after logout | Files remained on disk with matching hashes |
| Stop server | UI showed Disconnected, demo backoff retry and connection refusal; send controls disabled |
| Restart server | Both clients automatically reconnected; post-restart chat reached Alice and Bob showed DELIVERED |

Two bugs were reproduced and fixed before this verification completed:

- Rebuilding recipient options every second closed the native dropdown. Only
  rebuild when the recipient roster changes; retain a valid selection.
- Per-chunk progress events could exhaust the 500-event buffer while a tab was
  in the background, hiding chat/receipts. Keep only the latest progress event
  per type/file, with a fresh increasing event ID. Repeated binary transfer then
  retained chat before and after completion. A regression emits 4,000 progress
  updates and checks retained chat, separate transfers and increasing IDs.

Actual received file hashes (`Get-FileHash -Algorithm SHA256`), identical to source:

| File | Bytes | SHA-256 |
|---|---:|---|
| Báo cáo E2E.txt | 62 | `997131c833496aee95fe702038d84402b196b8e49e6156434416a7ec31623a01` |
| empty.txt | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| binary.bin / binary_1.bin | 2097152 | `1e075c8d478ad21844e33e830a695ef03a4d2488b69ee275bd8947618bb1be1e` |

Final automated checks: 62 Python tests passed, smoke PASS, 20-client load PASS,
Node DOM-double UI checks PASS. The DOM double also verifies unchanged polling
does not rebuild the recipient selector.

Scope: these browser results cover localhost **demo mode**. Account registration,
wrong-password/HTTPS browser behavior, certificate trust, account-mode outbox
replay, cross-account isolation, LAN, very large files and long-duration runs
remain manual browser checks. Account/TLS registration, persistence, ordered
outbox replay and isolation passed the real-socket Python tests; those results
are not claimed as browser E2E. No browser warning was bypassed or Chrome security
setting changed during verification. The existing packet capture is a separate
earlier integration run, not a capture of this browser session.
