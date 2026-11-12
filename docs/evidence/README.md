# Evidence provenance

`member4/` (13 PNGs) and `linux/` (3 PNGs) are unchanged artifacts selected from
`origin/feature/member4-ui`, commit `7319f68`. They show that branch's Windows UI
and Ubuntu Unicode-filename demonstrations. They are historical evidence, not
proof that the final integration's registration/outbox/TLS UI was browser-tested.

`captures/integration-loopback.pcapng` is a new actual Npcap loopback capture made
on 2026-11-12 while running `python -m scripts.wireshark_demo` on the integration
implementation. The capture filter restricted traffic to TCP 9100 / UDP 9101.
It contains only synthetic localhost demo traffic, not an exported AES key or TLS
private key. See `../wireshark_demo.md` for exact filters and observations.

The final browser E2E attempt was stopped by Computer Use because it could not
confidently determine the current Windows browser URL for policy enforcement.
No new integrated-browser screenshots or browser E2E pass are claimed.
