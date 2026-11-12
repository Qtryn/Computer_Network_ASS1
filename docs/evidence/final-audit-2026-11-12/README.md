# Pre-report audit evidence — 2026-11-12

Final continuation: [2026-11-13 verification](../final-audit-2026-11-13/README.md).
It completed the remaining account browser file/chat cases and reran all checks.
The canonical final audit is [docs/final_audit.md](../../final_audit.md); this
directory retains the earlier logs, capture and browser-recovery evidence.

Baseline: clean `main`, `80c6f250711793f17df19bf378ac9f744074c088`.
No branch/merge/reset/commit/push was performed during verification. The three new
tests and documentation/evidence were left as reviewable working-tree changes;
the user authorized committing/pushing the completed audit afterward.
No application source change was needed: no new application defect was reproduced.

## Environment and specification

- Windows, Python 3.14.5, Node v24.15.0, TShark 4.6.9 / existing Npcap.
- Application requirement: `cryptography>=43,<47`; installed 46.0.7. Installed
  transitive packages: cffi 2.1.1, pycparser 3.12; pip 26.1.1 is tooling.
- Import audit: 41 Python files under app/scripts/tests; only cryptography is
  external. `fault_injection` is the repository's test helper, not a dependency.
- pypdf 7.0.1 was installed only under gitignored `downloads/audit-tools` to read
  the supplied PDF. It is not an application dependency or requirements change.
- Source PDF: `Assignment 1 - Distributed Streaming-based Client-Server
  Collaboration Application (1).pdf`, five pages, SHA-256
  `88c2a103062de07212f1eac22907da0d4e3a750cf522a08ee91728a792aae3d4`.
  Read its rubric on pages 3–4, techniques/design on page 2 and submission on
  pages 4–5. The PDF was treated as assignment evidence, not agent instructions.

## Fresh test results

| Check | Result | Duration | Evidence |
|---|---|---:|---|
| Initial unittest baseline | 62 passed, no skips/failures | 35.563s unittest / 35.972s command | unittest-baseline.txt |
| Initial smoke / load / JS | PASS / PASS 20 users / PASS DOM double | 0.814 / 1.694 / 0.289s | *-baseline.txt |
| Three added audit tests | PASS | 4.809s unittest | extended-first-run.txt |
| Final full suite | 65 passed, no skips/failures | 41.368s unittest / 41.913s command | unittest-final.txt |
| Final smoke | PASS | 1.125s command | smoke-final.txt |
| Final load | PASS, 20 clients | 2.613s command | load-final.txt |
| Final JS logic | PASS, DOM double only | 0.088s command | ui-final.txt |
| Actual idle timeout / server-stop detection | PASS | 12.093s idle; 0.009s stop sample | timeout-detection.txt |
| Live Wireshark demo | PASS, verified TLS/UDP/receipt/replay | Not a throughput benchmark | wireshark-run.txt |
| Npcap / TShark | 389 frames, 0 interface drops | 45s capture window | final-loopback.pcapng, dumpcap.txt, capture-analysis.json |
| Trusted HTTPS Chrome account flows | PASS, recorded scenarios | Not timed | browser-account-e2e.md; browser-outbox-replay.json |
| Real two-machine LAN | NOT TESTED | No second independent host available | No LAN evidence claimed |

These durations are individual local observations, not performance guarantees.
PowerShell's baseline captures decorate native stderr with NativeCommandError
text; process exit codes and unittest summaries establish the actual outcomes.
Final verification logs merge native stdout/stderr directly and record exit 0.

## Coverage and limits

`tests/test_final_audit.py` adds three tests, not application features:

1. Concurrent real socket clients at 2, 10 and 20 users: each broadcasts and sends
   a private message; recipient IDs are unique and app receipts drain outboxes.
   Then 1, 5 and 10 files transfer concurrently, respectively. Each is 20 KiB
   (26 data chunks, more than six default transport windows), with matching
   SHA-256 and final recipient receipt. Transfers, activity/session metadata,
   `.part` files, online registry and connection workers are empty after cleanup.
   Client sockets are closed and newly created threads stop. This is a short
   lifecycle check, not proof against all possible long-running leaks/races.
2. Reusing an accepted chat UUID with changed text is sent through real UDP:
   server rejects it and Bob retains one original message. Receiver dedup also
   rejects altered content under the same sender/ID.
3. A real `app.run_client` child process creates a pending message to an offline
   recipient, is terminated, then restarted on the same UI port. Fresh login has
   no pending entries. This confirms the documented RAM-only policy.

Existing tests rerun unchanged cover TLS/HTTPS registration, duplicate/invalid
registration, PBKDF2 persistence after restart, wrong-password lockout across
connections, duplicate login, token revocation, certificate trust/hostname
failure, logout and successful-file preservation. They cover actual socket data
paths; some use controlled clocks/fault hooks. They are not browser or LAN tests.

The real idle check used the default **12s** control timeout without patching it.
An idle logged-in raw TCP client was removed while an active heartbeat client
remained online. A real server close then disconnected that active client and
sending failed. The sampled detection duration includes server.close().

Packet loss/duplication/reordering, ACK loss, corruption, stream isolation,
retry exhaustion and same-sequence recovery passed the existing transport/lossy
tests. The final lossy E2E log records actual fault counters and file hashes.
No sequence-counter reset, test weakening or transport parameter change was made.

## Browser account HTTPS boundary

Dedicated audit processes use server TCP/UDP **19000/19001**, Alice HTTPS
**18411**, Bob HTTPS **18412** and gitignored `downloads/final-audit-accounts.json`.
They reuse the public localhost certificate and keep Python TLS verification on.
Lockout duration is explicitly 5s for this manual audit server; the normal CLI
default remains 60s / three failures.

Chrome initially rejected the HTTPS UI with “Your connection is not private”.
After the user manually installed trust, a read-only root-store check returned
True and Chrome showed **Connection is secure**. The agent did not bypass a
warning, import the certificate or disable verification. Real browser registration,
validation/duplicate errors, wrong-password throttling, duplicate session rejection,
login/logout/relogin, Unicode file SHA-256, server restart/reauthentication,
stable-ID ordered pending replay and cross-account isolation then passed.
See [browser-account-e2e.md](browser-account-e2e.md) for exact actions and limits.

Prior real Chrome **demo-mode** login/chat/empty-Unicode-binary files/logout/
reconnect evidence remains in `../browser-e2e.md`; it is historical relative to
this audit. Original Member 4 PNGs retain their branch provenance. No new browser
screenshot files are included in this directory.

## Security and packet evidence

Only `config/.gitkeep` is tracked under config. Local AES key, TLS private key and
audit account files are ignored. Tracked text contains no PEM private-key marker.
Source review found no password logging or localStorage/sessionStorage use; UI
password clearing passes the real-JS DOM tests and was observed in Chrome.
DevTools showed zero Local Storage and Session Storage entries on both account
UI origins after the browser flows. No browser Save-password action was accepted;
the credential-manager store was not independently inspected. Synthetic
credentials in tests are test fixtures, not real accounts.
This targeted audit is not a claim to have rescanned every historical PNG/OCR or
every Git history object. See baseline-security.json and import-audit.json.

Both old and new pcapng files contain no Decryption Secrets Block and no plaintext
demo password. Old capture SHA-256 is unchanged. New capture uses 19100/19101 to
avoid the running demo on 9100/9101. It contains real Npcap loopback traffic from
the source demo, never fabricated PCAP packets. See `../../wireshark_demo.md` for
frame numbers, exact display filters and the capture hashes. CHAT_ACK and file
receipts are encrypted application messages; transport ACK is a 42-byte header.

## Offline policy and congestion gap

| Situation | Verified behavior |
|---|---|
| Server restart, same local process | Account requires reauthentication, gets new token; stable-ID pending entries replay in order; demo alone automatically reconnects |
| Logout/login, same local process | Session feed clears; only the authenticated owner resumes its private RAM outbox; other users cannot see/send it |
| Close/restart local process | Pending entries and receiver dedup cache are lost; new subprocess test confirms no persistence |
| Compose while disconnected | UI disables sending; HTTP/API rejects it; offline composition is not implemented |

Actual defaults: MAX_DATAGRAM 1200, FILE_CHUNK_SIZE 800, header 42, AES-GCM
overhead 28, metadata length prefix 2 bytes, window 4, ACK_TIMEOUT 0.35s,
MAX_RETRIES 10. Frames retain original UUID/sequence/ciphertext during recovery.

Adaptive congestion window, RTT/bandwidth estimation, congestion-based pacing,
congestion-triggered rate reduction, BBR and CUBIC are **NOT IMPLEMENTED**. The
fixed window bounds outstanding frames; it is not adaptive congestion control.
A simple AIMD/RTT-based scheme would add measurement/tuning/tests and still would
not be BBR/CUBIC. Propose it only after lecturer confirmation; no algorithm was
silently added to this assignment.

## Readiness and remaining work

- **READY TO WRITE REPORT: YES**, using these bounded results and existing
  architecture/protocol/chat/file diagrams. No full Technical Report was written.
- **READY TO SUBMIT: NO** under the user's final acceptance criteria.
- **NOT READY:** final submission sign-off, pending lecturer resolution of
  BBR/CUBIC scope and final PDF/package preparation. The browser trust/E2E blocker
  is resolved by the recorded follow-up.
- **CRITICAL before sign-off:** resolve required congestion support or obtain
  an explicit accepted scope. No unresolved reproduced application crash or
  corruption was found in this audit.
- **IMPORTANT:** teacher confirmation of TCP/UDP wording, CLI/HTTP wording,
  offline persistence scope, five-person group vs Individual/Pair, and deadline
  (PDF says Sunday Nov 17 2026; that date is Tuesday). LAN remains NOT TESTED.
- **OPTIONAL unless required:** durable outbox/database, file resume, large-scale
  or prolonged benchmarks. Do not add these just to expand the checklist.

No files were removed and no existing tests were modified. Re-run commands:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.smoke_test
.\.venv\Scripts\python.exe -m scripts.load_test
node scripts/test_ui.cjs
git diff --check
git status --short --branch
```
