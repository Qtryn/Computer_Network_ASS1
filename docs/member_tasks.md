# What each member must do next

This is a realistic work plan based on the team's allocation file.

## Member 1 — Server / integration (owner: unassigned)

**Current runnable baseline:** TCP login/heartbeat, registry, relay and threaded
clients in `app/server/`.

- [ ] Confirm with teacher: hybrid TCP/UDP, group size and final deadline.
- [ ] Validate session cleanup when a client is killed, not only graceful logout.
- [ ] Review handling of duplicate usernames and invalid control JSON.
- [ ] Limit and expire unfinished file-transfer routing metadata.
- [ ] Review shared protocol/ports with Member 2 before teammates start making changes.
- [ ] Rerun the included 20-client localhost test; extend and test on actual LAN.
- [ ] Prepare high-level architecture and overall state diagram for report.

## Member 2 — Reliable UDP transport (owner: unassigned)

**Current runnable baseline:** packet framing, per-stream sequence and in-order
queues, ACKs, duplicate filtering, retransmissions and fixed 4-packet window.

- [ ] Confirm with teacher exactly what BBR/CUBIC support means for this project.
- [ ] Implement and benchmark the agreed congestion-control approach if required.
- [ ] Add receiver backpressure/flow control suitable for very large file transfers.
- [ ] Bound/reclaim old stream/reorder/deduplication state during extended use.
- [ ] Expand reproducible UDP loss, delay, duplication and reordering tests.
- [ ] Confirm that chat remains responsive while a large file is transferred.
- [ ] Prepare sequence diagram for ACK, retries and ordering.

## Member 3 — Chat and files (**your module**)

**Current functional implementation:** `chat.py` and `files.py` with broadcast,
private routing, file START/CHUNK/END, SHA-256 and filename validation.

- [x] Implement clear chat message creation and target routing.
- [x] Implement streaming file reading rather than loading whole file into RAM.
- [x] Implement chunk reassembly, size/index checks, binary/empty-file support.
- [x] Verify SHA-256 before exposing final received file.
- [x] Add unit tests for success, corrupt payload and path traversal names.
- [ ] Add a practical file-cancel/time-out cleanup policy with Member 1/Member 2.
- [ ] Repeat tests with bigger files, Unicode names and a receiver disappearing.
- [ ] Agree on transfer progress/final receipt events with Member 4.
- [ ] Describe chat/file sequence and sample hash output in report.

**You should not rewrite TCP handshake, UDP ACK/retries, or browser UI.** Those
belong to Member 1/Member 2/Member 4. If a shared API must change, open a team review first.

## Member 4 — Client and browser UI (Thanh Bình)

**Current runnable baseline:** local HTTP service and HTML/JS UI; send chat/file,
active users and progress display.

- [x] Test browser on Windows and Ubuntu Linux, including uploading files with
  Vietnamese filenames; Linux evidence is in `docs/evidence/linux/`.
- [x] Show a clear local-client-unavailable state, clear stale users and disable
  sending controls; the UI polling restores them when the client is available again.
- [x] Distinguish sender-to-server transport ACK progress from recipient receipt
  and SHA-256 verification in the progress label.
- [x] Keep sent chat visible in the sender's feed and avoid duplicate broadcast
  echoes.
- [x] Add a browser login form and connect the client to the collaboration
  server from the UI; retain `--name` as an optional pre-login mode.
- [x] Add a logout action that closes the client session and returns to login.
- [x] Review layout/usability from Windows demo screenshots.
- [x] Capture demonstration screenshots in `docs/evidence/member4/` and
  `docs/evidence/linux/`.
- [ ] Confirm local HTTP + JS is an acceptable interpretation of rubric step 9.
- [ ] Coordinate any changes to the `CollaborationClient` API with Member 3.

## Member 5 — Crypto + tests + packaging (nquan)

**Current runnable baseline:** AES-GCM payload encryption and unit tests, SHA
integrity checking in Member 3, localhost end-to-end smoke test.

- [ ] Document safe distribution of the shared test key without committing it.
- [ ] Review packet tampering/wrong-key tests at the actual UDP layer.
- [ ] Extend `scripts/load_test.py` with timing/logs and actual LAN trials.
- [ ] Add controlled loss, delay, duplication and disconnection scenarios.
- [ ] Verify files from a fresh clone on another PC, not just own machine.
- [ ] Assemble README, evidence and 1-page Challenges & Solutions section.
- [ ] Coordinate report PDF, diagrams and submission archive.

## Before declaring 10/10

All ten lines of `RUBRIC_CHECKLIST.md` should have **actual, reproducible test
evidence**, not just documentation promises or code TODO comments.
