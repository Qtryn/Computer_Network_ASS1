# Evidence image slots - replace on Overleaf

The LaTeX report intentionally displays amber `EVIDENCE TO INSERT` frames until a file with the exact name below is uploaded into this directory. No fake image or fabricated test evidence is included.

| File | What your own screenshot must show | Location in report |
|---|---|---|
| `01_https_login_roster.png` | Trusted HTTPS account-mode Chrome UI after successful login, with online users visible; crop out credentials and tokens | Testing section |
| `02_chat_file_verification.png` | Current `main` UI: private/broadcast chat or a file transfer showing `FILE_RECEIPT` and SHA-256 verified (or a composite of two current real screenshots) | Testing section |
| `03_pending_before_restart.png` | Real account-mode sender with PENDING messages, while server is unavailable; no passwords visible | Recovery subsection |
| `04_delivered_after_relogin.png` | Same client/account after real server restart + password re-login, matching messages marked DELIVERED, without duplicates | Recovery subsection |
| `05_wireshark_udp_retransmission.png` | Open `docs/evidence/final-audit-2026-11-12/final-loopback.pcapng` in Wireshark. Show DATA frames 109 and 120 with same UUID/sequence and ACK frame 121. Capture uses TCP 19100 / UDP 19101. If packet numbering differs, caption must be updated. | Testing section |
| `06_tests_and_concurrency.png` | Legit terminal output with 65/65 unittest and 20-client load test PASS (combine two cropped genuine screenshots if needed) | Testing section |

Optional: add a genuine screenshot proving chat visible before a 2-MiB file finishes, or a 2-host LAN test; if absent, current text states actual recorded result and no LAN claim.

## How to populate
1. Export each screenshot from the **current integrated main** application or saved capture, preferably PNG. Do not use historical `feature/member4-ui` photos as proof of the latest account-mode UI.
2. Crop tightly; redact **all secrets, account passwords, session tokens, AES keys and private key data**.
3. Upload into this `evidence` folder with exact filenames. Recompile `main.tex` twice with pdfLaTeX. The amber frame automatically becomes the screenshot; figure captions and labels are already included.
4. Verify readability at normal PDF zoom. Replace in the source or crop differently if details are too small.
5. Fill in instructor confirmation items in Section 7 before producing the final submission PDF; delete any no-longer-applicable reminder blocks.
