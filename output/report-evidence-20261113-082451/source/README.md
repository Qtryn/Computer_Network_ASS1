# HCMUT - Assignment 1 Technical Explanation Report

This is an editable LaTeX source package using the team's original
`hcmut-report.cls` and original HCMUT logo from the uploaded
`LAB1_ComputerNetwork.zip`.

## Compile

On Overleaf: upload the ZIP, set `main.tex` as the main document and use **pdfLaTeX**.

Locally (TeX Live with `vntex`, TikZ, cleveref):

```bash
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

## Files

- `main.tex`: report metadata, author list, formatting, section inputs.
- `sections/*.tex`: editable report text.
- `diagrams/*.tex`: editable TikZ architecture and sequence diagrams.
- `hcmut-report.cls`: the original university class from your team ZIP.
- `graphics/hcmut.png`: original university logo from your team ZIP.

## Fill the highlighted screenshot slots before final submission

This edition is intentionally a **draft with amber/yellow evidence placeholders**. The PDF is
compile-ready but the missing figures must be supplied by the team. To fill them, add authentic
PNG screenshots under `evidence/` using the six exact filenames listed in
[`evidence/README.md`](evidence/README.md). Recompile twice. A screenshot file automatically
replaces its amber frame; no source-code edits are necessary.

There are six slots:

1. Trusted HTTPS login and roster (`01_https_login_roster.png`).
2. Current-version chat/file verification (`02_chat_file_verification.png`).
3. Pending messages before server restart (`03_pending_before_restart.png`).
4. Delivered messages after password re-login (`04_delivered_after_relogin.png`).
5. Wireshark UDP retransmission/ACK (`05_wireshark_udp_retransmission.png`).
6. Final 65-tests + 20-client terminal evidence (`06_tests_and_concurrency.png`).

Section 7 additionally highlights the instructor/administrative checks still unresolved:
BBR/CUBIC scope, client-process restart and RAM outbox scope, five-person group authorization,
and the actual LMS deadline. Two-host LAN is optional unless required. Do not state these are
completed without verification. Remove reminder frames only after action/confirmation.

**Do not submit this draft PDF with unfilled amber evidence placeholders.**

## Grounding and limits

Report source code is based on repository `Qtryn/Computer_Network_ASS1`, application revision
`80c6f25`, with committed final-audit evidence revision `cfe60cd` (Nov 13, 2026).
The 65-test results and captures are *team-recorded* checks in the repository.
The report does not claim BBR/CUBIC, durable offline queues or a two-host LAN test.

Advisor and five student names/IDs were reproduced from the uploaded previous
report covers; verify these administrative details before final submission.

PDF is a report deliverable, not a claim that the repository is ready for an
unconditional submission. Confirm instructor acceptance for group size and
congestion-control scope.
