# Genuine report screenshots — 2026-11-13

All six required images are **CAPTURED** from real application, terminal, or Wireshark windows. No UI rows, success output, or packet bytes were recreated. Cropping and panel labels identify unchanged source pixels. Full-window originals and exact crop recipes are retained.

## Execution context

- Repository: `Qtryn/Computer_Network_ASS1`, existing `main`.
- Application commit: `cfe60cd3996f235b65f9cd05726e3750c492232d`.
- Run: `20261113-082451`; date: **2026-11-13**, timezone **Asia/Saigon (UTC+07:00)**.
- Windows, PowerShell, project `.venv` Python **3.14.5**, cryptography **46.0.7**, cffi **2.1.1**, pycparser **3.12**, Node.js **24.15.0**; installed Wireshark/TShark **4.6.9**.
- Verified TLS account server: `127.0.0.1:19000/TCP`, `19001/UDP`; real Chrome HTTPS interfaces: `https://127.0.0.1:18411` (Alice), `https://127.0.0.1:18412` (Bob).
- Existing `config/local_tls/server.pem` was used as the client CA and UI certificate. No verification bypass, browser warning bypass, certificate-store change, production source change, runtime dependency change, commit, merge, or push was performed.
- Synthetic accounts: `report_alice`, `report_bob`. Passwords are absent from evidence. The user registered and logged in manually, then logged in Bob before Alice after server restart.

## Image inventory

Paths below are relative to this directory. Every row uses the date, commit and environment above. Each PNG is also copied byte-for-byte to the separate report source's `evidence/` directory.

| Filename | Status | Source and observed result | Related records | Capture / manual interaction |
|---|---|---|---|---|
| `01_https_login_roster.png` | **CAPTURED** | Actual Chrome Alice UI: Account/TLS, Connected, both users online, chat/file controls. Address and controls are cropped from one original; blank feed space omitted. | `originals/20261113-082451/01_alice_connected_full.png`; `logs/20261113-082451/02-chat-file.json` | Automated native screenshot/crop after user opened HTTPS tabs and completed registration/login. |
| `02_chat_file_verification.png` | **CAPTURED** | Actual Alice/Bob browser crops: private and broadcast DELIVERED; each incoming chat once; receiver SHA-256 verification and successful sender FILE_RECEIPT. | `02a_alice_chat_receipt_full.png`, `02b_bob_received_full.png` under originals; `logs/20261113-082451/02-chat-file.json`; `evidence-validation.json` | Automated real browser actions, actual file chooser, native screenshots and combination; credentials entered by user. |
| `03_pending_before_restart.png` | **CAPTURED** | Actual Alice UI: Pending chats 2; replay A and B PENDING; delivery-uncertain errors. Both enqueued while Connected. | `originals/20261113-082451/03_alice_pending_full.png`; `logs/20261113-082451/03-before-restart.json`; `controlled-loss.txt` | Automated test-only outgoing CHAT DATA loss and screenshot; no production networking edit. |
| `04_delivered_after_relogin.png` | **CAPTURED** | Actual Alice/Bob crops after normal server restart: both Connected; Alice pending 0 and A/B DELIVERED; Bob one row each, A before B. Original UUIDs match. | `04a_alice_delivered_full.png`, `04b_bob_replay_full.png` under originals; `logs/20261113-082451/04-after-relogin.json`; `replay-validation.json`; `evidence-validation.json` | Automated server restart and screenshots. User reauthenticated Bob, then Alice; both original local UI processes stayed alive. |
| `05_wireshark_udp_retransmission.png` | **CAPTURED** | Actual Wireshark packet-list/header crops: DATA 109/120 identical; ACK 121 has matching UUID/sequence and reversed ports. | Three `05*_wireshark_frame*_full.png` originals; preserved PCAP below; `logs/20261113-082451/pcap-selected-frames.tsv`; `pcap-sha256.txt`; `evidence-validation.json` | Automated TShark verification, Wireshark Open/filter/select and genuine native captures; no new capture claimed. |
| `06_tests_and_concurrency.png` | **CAPTURED** | Genuine real terminal: `Ran 65 tests in 44.532s`, `OK`, and `PASS: 20 concurrent clients, online list and private chat`. | `originals/20261113-082451/06a_unittest_full.png`, `06b_load_full.png`; complete logs below | Automated subprocesses streamed their actual output to a visible terminal. User restored the terminal once for capture; two genuine crops combined. |

## Current test results

Executed from the project root using the actual virtual environment; complete stdout/stderr retained in `logs/20261113-082451/`.

| Command | Observed result | Command elapsed | Log |
|---|---|---|---|
| `.\.venv\Scripts\python.exe -u -m unittest discover -s tests -v` | **65/65 PASS**, suite time 44.532 s | 45.398 s | `unittest.txt` |
| `.\.venv\Scripts\python.exe -u -m scripts.smoke_test` | **PASS**: login, roster, private/broadcast, binary UDP file, hash, receipt, logout | 1.216 s | `smoke.txt` |
| `.\.venv\Scripts\python.exe -u -m scripts.load_test` | **PASS**: 20 concurrent localhost clients, roster and private chat | 2.168 s | `load.txt` |
| `node scripts/test_ui.cjs` | **PASS**: UI logic using a DOM double; separate actual Chrome evidence is provided above | 0.275 s | `ui.txt` |

All four commands exited **0**. Timings are this recorded run, not performance guarantees. `test-summary.json` preserves command exit codes and durations. Actual Chrome was used for screenshots 01–04; the JavaScript test alone is not browser E2E evidence.

## Chat, file and recovery checks

- Private UUID: `036c49e3-0f93-445d-8ecf-746c9af6a805`; broadcast UUID: `df2dd16b-b841-46a4-bf40-c7086f58ec9b`. Bob had exactly one CHAT event for each.
- File: synthetic `report-demo.txt`, **82 bytes**; actual chooser upload, completed at Bob as `downloads/report_bob/report-demo.txt`.
- Source and received SHA-256: `5e1f3eafd151f5066b36d43bfef25ad21a2d5d3ee652b480d6ae04424b080785`.
- Successful sender FILE_RECEIPT: file UUID `70a07a9d-8390-4405-bc56-3662e8be8009`, sender `report_bob`, status `ok`, message `SHA-256 verified`.
- Pending order before restart: A `af41c9a6-1d96-4467-b196-cb4d3d525b51`, then B `38837275-f027-4a64-b894-824cd9f0fa2d`.
- After restart/relogin, Bob's two CHAT events have exactly those UUIDs, in that order, once each. Alice has one DELIVERED receipt per UUID and empty outbox.
- Loss harness: task-only `downloads/report-evidence-20261113-082451/report_server.py`, adapted after inspecting the existing audit harness. It drops outgoing encrypted CHAT DATA for `report_alice` only while the task's flag exists. It does not change application source. The flag was removed and a normal `app.run_server` process used for replay.
- This proves replay only while the same local UI processes stay alive. It does **not** prove disk persistence, client-process restart recovery, offline composition, separate-host LAN performance, or BBR/CUBIC.

## Preserved Wireshark capture

Original remains unchanged: `docs/evidence/final-audit-2026-11-12/final-loopback.pcapng` (repository-relative). It is an earlier real audit capture, freshly inspected on 2026-11-13, not traffic from this screenshot session.

- SHA-256: `e9acddbab2bba4ddf4a7d79240d31ebf7f7a46bb4c63823de2f54a63b3ff75f4`.
- Wireshark shows **389 total frames**, **3 displayed** using `frame.number == 109 || frame.number == 120 || frame.number == 121`.
- DATA 109 and 120: UDP `56417 -> 19101`, payload 324 bytes, byte-identical payload SHA-256 recorded in `evidence-validation.json`.
- ACK 121: UDP `19101 -> 56417`, payload 42 bytes.
- All three: packet UUID `82bc661c-2bf6-4a47-83e5-490095401c5a`, stream UUID `e2c65fb0-ece7-a1ac-0470-52fff80fa2dc`, sequence **0**.
- In the actual packet-byte crops, custom header begins at packet offset **0x20**. Kind is at **0x25** (01 DATA, 02 ACK); sequence is **0x26–0x29**; packet UUID is **0x2a–0x39**. Header offsets are interpretation of genuine bytes, not Wireshark-dissected custom fields. No `tcp.analysis.retransmission` filter was used to infer UDP retransmission.

## Originals, recipes and validation

- Unchanged full-window originals: `originals/20261113-082451/`.
- Exact source rectangles, positions and labels: `tools/20261113-082451/*-crops.json` and `06-crops.json`; native capture and lossless crop scripts are retained alongside them.
- `06a_unittest_original.png` was an initial **partial/minimized-window capture** and is retained only as an attempt trace. It is not used in any final image. `06a_unittest_full.png` is the genuine complete replacement captured after manual restore.
- Six final PNG dimensions/SHA-256 values, mirrored-image equality, test exits, file hash, original/replayed IDs and decoded packet headers: `logs/20261113-082451/evidence-validation.json` (**PASS**).
- Screenshots were viewed individually after capture/combination. No credential, key, token or password is in the final PNGs.

## Report source and compilation status

- Original user archive untouched: `C:/Users/quang/Downloads/HCMUT_Assignment1_LaTeX_With_Evidence_Placeholders.zip`.
- Separate updated source: `C:/Users/quang/Desktop/MMT_LAB/output/report-evidence-20261113-082451/source/`.
- Primary six PNGs: that source's `evidence/` directory; mirrors: `C:/Users/quang/Desktop/MMT_LAB/docs/evidence/report-screenshots/`.
- All **six exact LaTeX evidence references resolve**. In the separate copy, the screenshot figures use full text width with larger height limits; captions identify actual runs and genuine crops. Earlier audit timings remain distinguished from this rerun.
- **PDF NOT COMPILED / rendered layout NOT VERIFIED**: `pdflatex`, `latexmk`, and `tectonic` were unavailable on Windows PATH/common MiKTeX/TeX Live paths and the existing Ubuntu WSL distribution. No compiler was installed and no report was uploaded externally. Build `main.tex` with pdfLaTeX twice in a configured environment (e.g. Overleaf); package requirements come from the existing class/source.
- All highlighted outstanding requirements concerning BBR/CUBIC, offline persistence and lecturer confirmation remain in the source. Images do not resolve those limitations.

## Manual interaction and cleanup

The user opened the real HTTPS tabs, restored the genuine test console, registered/logged in both synthetic accounts, and reauthenticated Bob then Alice after restart. Automatic approval review rejected automated new-credential entry/submission and required this handoff; the user completed it, so no screenshot remains blocked by authentication.

After preserving and validating the results, only the task-owned fault server, normal replacement server, both client UI processes and visible test-console runner were shut down. Test ports 19000/TCP, 19001/UDP, 18411/TCP and 18412/TCP no longer have listeners. Browser tabs and the opened Wireshark trace remain available for inspection. No production application files were changed or pushed.
