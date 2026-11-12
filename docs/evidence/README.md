# Evidence provenance

Latest verification: [final-audit-2026-11-13/](final-audit-2026-11-13/README.md).
It contains the fresh 65-test/smoke/load/UI logs and the final HTTPS account
broadcast/empty/binary/concurrent-chat observations and hashes. Overall readiness
is recorded in [final_audit.md](../final_audit.md). Earlier artifacts are preserved.

The fresh pre-report audit is in
[`final-audit-2026-11-12/`](final-audit-2026-11-12/README.md): clean baseline SHA,
62-test baseline and 65-test final logs, expanded 2/10/20-client scenarios,
real process-restart RAM policy check, actual idle timeout, import/security audit
and a separate new 389-frame Npcap capture. It records browser trust and LAN
limits separately; existing artifacts below were not overwritten.

`member4/` (13 PNGs) and `linux/` (3 PNGs) are unchanged artifacts selected from
`origin/feature/member4-ui`, commit `7319f68`. They show that branch's Windows UI
and Ubuntu Unicode-filename demonstrations. They are historical evidence, not
proof that the final integration's registration/outbox/TLS UI was browser-tested.

`captures/integration-loopback.pcapng` is a new actual Npcap loopback capture made
on 2026-11-12 while running `python -m scripts.wireshark_demo` on the integration
implementation. The capture filter restricted traffic to TCP 9100 / UDP 9101.
It contains only synthetic localhost demo traffic, not an exported AES key or TLS
private key. See `../wireshark_demo.md` for exact filters and observations.

The initial browser attempt was stopped by URL-confidence enforcement. A later
real Windows Chrome retry verified the integrated localhost demo flows and found
two UI/event-buffer bugs, now fixed. See [browser-e2e.md](browser-e2e.md) for that
demo record. A further trusted HTTPS Chrome account run passed registration,
login/logout, restart, ordered pending replay and identity isolation; see
[browser-account-e2e.md](final-audit-2026-11-12/browser-account-e2e.md). No new
screenshot files are included; imported images remain historical evidence.
