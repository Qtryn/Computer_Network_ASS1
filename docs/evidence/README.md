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

The initial browser attempt was stopped by URL-confidence enforcement. A later
real Windows Chrome retry verified the integrated localhost demo flows and found
two UI/event-buffer bugs, now fixed. See [browser-e2e.md](browser-e2e.md) for actual
observations, file hashes and the remaining account/HTTPS browser scope. No new
screenshot files are included; imported images remain historical evidence.
