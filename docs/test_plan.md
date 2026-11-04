# Repeatable test plan and evidence checklist

## Automated tests

From the repository root:

```bash
python -m unittest discover -s tests -v
python scripts/smoke_test.py
python scripts/load_test.py
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
