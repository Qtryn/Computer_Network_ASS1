# Repeatable test plan and evidence checklist

## Automated tests

Initial finalization on 2026-11-12 verified 28 -> 41 tests. Integration started
from that clean 41-test main. No existing tests were removed or skipped.
Final integration verification: **62/62 Python tests**, smoke test, 20-client
load test and JavaScript DOM-double checks passed. Real capture demo passed;
TShark independently verified 373 packets and repeated DATA/ACK packet IDs.
Import audit of 40 Python files found only
`cryptography` (installed version 46.0.7) outside the standard library/project.

From the repository root:

```bash
python -m unittest discover -s tests -v
python -m scripts.smoke_test
python -m scripts.load_test
node scripts/test_ui.cjs
```

Capture the terminal output without hiding errors. The `smoke_test.py` opens
real localhost TCP and UDP sockets. `load_test.py` opens 20 clients. It checks Alice/Bob login, online users,
private and broadcast chat, binary-file SHA-256, receipt and logout.

## Manual functional tests (M1–M2)

1. Start the server and two clients using README instructions.
2. Both UIs must list Alice and Bob; take a screenshot.
3. Alice → Bob private chat; verify Bob receives it but no third user does.
4. Alice → Everyone broadcast; verify Bob and (if connected) Cindy receive it.
5. Send a non-empty text file, a binary file and an empty file to Bob.
6. Compare SHA-256 using `python -c` or Windows `Get-FileHash` against the
   original file; receiver should also show `FILE_COMPLETE`.
7. Send a chat message during a file transfer and observe the UI status.

## Resilience tests (M3, to extend)

- Close the Bob terminal without sending LOGOUT: check server removes Bob after
  heartbeat timeout and does not crash.
- Repeat file send with artificial 1-in-N UDP drops and added delay using Member 2's
  test hooks. Record lost packets, retries and final hash.
- Confirm duplicate UDP packets do not duplicate chat/file content.
- Start 10–20 distinct clients, record concurrent login and chat tests.
- Try corrupted ciphertext/wrong AES key: message must be rejected.
- Repeat one whole scenario on two LAN machines; document host IP and ports.

## Submission evidence

- [ ] Screenshot: two or more active users and online list
- [ ] Screenshot: private + broadcast messages
- [ ] Screenshot: file progress and completed receiver file
- [ ] Hash matches for multiple formats and empty file
- [ ] Terminal output: packet drops and retransmission
- [ ] Evidence: 10–20 concurrent client simulation
- [ ] Evidence: server remains running after unexpected client disconnect
- [ ] Sequence diagrams: chat and file/ACK
- [ ] Architecture diagram and protocol packet table
- [ ] README tested from a fresh cloned copy
- [ ] A one-page Challenges & Solutions section in final PDF

The report must reflect what the code actually does. Do not invent throughput,
loss rates, client counts or screenshots.

## Session/security regression checks and remaining browser work

`tests/test_client_sessions.py` uses real TCP/UDP and TLS sockets, including a
TLS-wrapped local HTTP request, then the Python client and collaboration server.
It checks invalid/passwordless login, certificate trust and hostname mismatch,
duplicate sessions, HTTP chat and empty/text/binary uploads, SHA-256, logout,
revoked tokens, clean relogin, abrupt TCP loss, sender/receiver disconnect and
timeout cleanup. Other clients' events and completed files must survive cleanup.
Transport regressions cover retry exhaustion and recovery, lost ACKs, ACK socket
failure, malformed/oversized packets, late duplicates and in-order delivery.

`scripts/test_ui.cjs` runs the real inline JavaScript against a small DOM double.
It checks password clearing, error visibility, password entry while polling,
logout history/recipient/progress reset, relogin and stale-response guards. It also
checks registration/password clearing, detailed file labels and stable-ID outgoing
dedup/status rendering. The integration tests add atomic persistent registration,
ordered outbox replay after a server restart, recipient application ACK loss,
cross-account isolation and reuse of the previous session's UDP port.
It does **not** prove browser rendering, browser security or file chooser behavior.

The first browser attempt was blocked by URL-confidence enforcement. A later real
Windows Chrome retry passed localhost demo-mode login/roster, private/broadcast
chat, native file chooser for empty/Unicode/binary files, SHA-256 receipts, chat
during binary transfer, logout/relogin and demo reconnect after server restart.
It also verified fixes for polling closing the dropdown and progress events
evicting chat. See [evidence/browser-e2e.md](evidence/browser-e2e.md) for observations
and hashes. The following broader **account-mode** / LAN checks remain manual
using the README account-mode commands:

- [ ] Configure browser trust for the locally generated certificate (or use an
      already trusted certificate). Open both HTTPS UI ports with no TLS error.
- [ ] Wrong password shows an error and clears the password field; correct
      credentials display username and both online users. Demo mode says no password.
- [ ] Broadcast/private chat goes to the intended peers; outgoing server ACK and
      recipient application receipt have distinct labels. Offline recipient stays
      PENDING and shows the error; recipient return allows ordered retry.
- [ ] Use the file chooser for empty/text/binary files; see progress, receiver path
      and sender's SHA-256 receipt; compare with `Get-FileHash -Algorithm SHA256`.
- [ ] Send chat during a sufficiently large transfer; chat appears before file completion.
- [ ] Logout clears feed, message/file inputs, cursor, recipient and progress;
      sending is disabled. Other UI goes offline; completed files remain on disk.
- [ ] Login again on the same page; no old messages reappear. Repeat logout;
      close a network connection and verify disconnected status and clean relogin.
- [ ] Register through HTTPS, reject duplicate/invalid accounts and log in after
      server restart. Confirm no password is saved in browser storage.
- [ ] Lose the server during chat, restart it, log in as the same account and
      observe the same pending message IDs become DELIVERED in order, once each.
- [ ] Log in as a different account after logout; no previous account's pending
      text appears or is transmitted. Closing the local process loses its RAM outbox.
- [ ] Repeat on two LAN machines with correct certificates, then collect screenshots.

Actual packet evidence is available separately: `evidence/captures/integration-loopback.pcapng`
contains 373 captured loopback frames, including repeated encrypted DATA after a
controlled lost ACK. See `wireshark_demo.md` for filters, frame numbers and SHA-256.
The 16 Member 4 Windows/Ubuntu images retain their original branch provenance.
