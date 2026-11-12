# Trusted HTTPS browser account verification — 2026-11-12

The follow-up on 2026-11-13 completed the remaining account broadcast, empty and
2 MiB binary browser transfers plus chat during transfer. See
[the final verification record](../final-audit-2026-11-13/README.md). Original
observations and limits below describe this earlier run.

Follow-up to the initial certificate blocker. Windows Chrome was operated through
Computer Use against `https://127.0.0.1:18411/` and `:18412/`; account server used
TCP 19000 / UDP 19001. Application source stayed at `80c6f25`. These are actual
browser observations, with complementary read-only HTTPS state and disk checks;
they are not DOM-double results. No screenshot files were exported.

## Trust and registration

The user manually installed trust for the existing public localhost certificate.
A read-only Windows root-store check returned True. Chrome displayed normal site
information and **Connection is secure**, with no warning bypass by the agent.
Python clients retained verified server TLS and the local adapter retained HTTPS.

| Browser action | Observed result |
|---|---|
| Register `bad name` | Rejected: username must be 1–20 letters/digits/underscores; password cleared |
| Register `test_bob` with a short password | Rejected: password must contain 8–128 characters and not be blank; password cleared |
| Register `test_bob`, then `test_alice` with synthetic valid passwords | Account created; instructed to reenter password and Login; no automatic login |
| Register `test_bob` again | Rejected: Username already exists |
| Login Bob with wrong password three times | Invalid-password errors, then Account temporarily locked; password cleared |
| Login Alice correctly | Connected; username and roster visible |
| Login Alice from Bob's local UI while Alice online | Rejected: Username already online |
| Login Bob correctly after lockout expires | Connected; both users online |

The dedicated audit server used a 5-second lock duration for this run. Application
defaults remain three failures / 60 seconds. The two browser-created accounts
were saved to gitignored JSON with only `salt` / `hash` fields. Synthetic password
text was absent. A later isolation test registered a third synthetic account,
`test_other`; final JSON still contained only salted hashes, not plaintext.

## Chat, file and logout

- Bob selected Alice and sent `HTTPS private before logout 01`. Bob showed one
  outgoing DELIVERED row and Alice showed one incoming row.
- Bob used the native file chooser to send `Báo cáo E2E.txt`. The sender showed
  server chunk ACK separately from recipient SHA-256 verification. Alice showed
  the completed path. Source and received 62-byte file SHA-256 matched:
  `997131c833496aee95fe702038d84402b196b8e49e6156434416a7ec31623a01`.
- Alice Logout emptied feed, reset recipient/progress to Everyone/0%, cleared
  inputs and disabled sending. Bob remained Connected with his own history; his
  roster showed only Bob. The completed file remained intact.
- Alice Login on the same page showed a fresh local session ID and no prior chat.
  Fresh server authentication token rotation is covered by real-socket tests;
  the browser does not expose its authentication token.
- Stopping/restarting the server disconnected both account UIs. They displayed
  Disconnected / log in again, with sending disabled. Restart alone did not
  authenticate them; user-entered passwords were required. Both accounts logged
  in from the persistent JSON store without restarting their local UI processes.

## Real browser pending-message recovery and identity isolation

The temporary `browser-fault-harness.py` uses the real application server and
TCP/TLS/UDP sockets. Its `_sendto` hook deliberately discards only outgoing CHAT
DATA whose sender is `test_alice` while a local flag exists. It does not fabricate
receipts, replace the browser, weaken authentication or change application code.
The console excerpt records actual blocked packet UUIDs/sequences. It is a
truncated, PTY-wrapped excerpt, not a complete packet capture. The flag was removed
after the test, and the final server is normal `app.run_server` without the hook.

The actual harness invocation set `PYTHONPATH` to the project root before running
the temporary script. To reproduce with the preserved copy, use the existing test
accounts, stop the normal server on 19000/19001, create
`downloads/browser-drop-chat.flag`, and run from the project root:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -u docs/evidence/final-audit-2026-11-12/browser-fault-harness.py
```

Stop this test server and restart the normal account server to restore delivery;
remove the flag after testing. The normal application server never reads the flag.

1. Using Chrome, Alice sent `HTTPS pending first 02` and `HTTPS pending second 03`.
   Her UI showed two pending entries (oldest SENDING/PENDING, second PENDING),
   delivery-uncertain errors and no DELIVERED receipt. Bob's feed had neither.
2. Complementary read-only HTTPS state checks recorded the stable message IDs:
   `5c011462-6dc1-43f4-af72-dff2f77e0bb8` and
   `3ea758ad-2f61-4880-8701-b9d442006724`.
3. The fault-injected server was stopped and normal account server restarted on
   the same ports. Bob authenticated first; Alice's outbox remained in the same
   local process, hidden while logged out/disconnected.
4. In Alice's local UI, a new authenticated `test_other` account showed Pending
   chats: 0 and only its own login event. Neither pending text was visible or
   transmitted to Bob. Then `test_other` explicitly logged out.
5. Alice authenticated again in that same local UI. Both original IDs were
   replayed in their original order. Alice showed two DELIVERED rows and Pending
   chats: 0. Bob showed exactly one incoming row for each, first then second.
6. Read-only HTTPS state checks matched received IDs and DELIVERED receipt IDs
   exactly to the saved queue. See `browser-outbox-replay.json`.

The controlled browser case drops CHAT DATA. Lost CHAT_ACK, duplicate packets and
receiver dedup after lost app ACK are covered separately by the passing real-
socket suite; this browser record does not relabel them as browser scenarios.

## Browser storage and evidence limits

After the above login/relogin/restart flows, Chrome DevTools Application panel
was used to inspect both origins. Local Storage and Session Storage each showed
**Number of entries shown in table: 0** on both 18411 and 18412 (four empty tables).
Password inputs were masked and cleared after attempts. No Save-password action
was accepted; the OS/browser credential store was not independently inspected.
DevTools was closed after inspection; both account clients remain Connected.

`browser-account-security.json` and `browser-account-file-hashes.json` store
noncredential results only. No password, session token, AES key, account hash or
TLS private key is included. The existing 389-frame capture belongs to the earlier
socket demo run, not this browser session. Original Member 4 images remain
historical. Account-mode empty/large binary file browser permutations and
two-machine LAN were not repeated here; demo browser/file tests and real-socket
tests cover those file cases within their stated scope.

Result: **PASS for the recorded trusted HTTPS registration/login/logout,
Unicode file, account restart/reauthentication, ordered outbox replay and account
isolation flows**. This resolves the previous browser trust blocker. It does not
resolve BBR/CUBIC, lecturer scope questions, LAN evidence or the final report PDF.
