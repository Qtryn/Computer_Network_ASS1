# Real packet capture demonstration

## Captured evidence (2026-11-12)

Open `evidence/captures/integration-loopback.pcapng` in Wireshark. This is an
actual Npcap loopback capture, generated with synthetic accounts/files by
`python -m scripts.wireshark_demo`, not a simulated trace or screenshot.
TShark observed **373 frames: 162 TCP, 211 UDP**; 62 frames were decoded as TLS.
The capture tool reported zero interface drops. SHA-256 of the capture:

```text
5bfbf838cc898aa92e2bfbb4ac72f3b1eb85746ffc82654a06101bf5e1a28a4c
```

Useful display filters:

```text
tcp.port == 9100 || udp.port == 9101
tcp.port == 9100 && tcp.flags.syn == 1
tcp.port == 9100 && tls
udp.port == 9101 && udp.payload[0:4] == 43:4f:4c:42 && udp.payload[5] == 1
udp.port == 9101 && udp.payload[0:4] == 43:4f:4c:42 && udp.payload[5] == 2
```

Packet 1 is the initial SYN, packet 2 its SYN/ACK. Fresh SYNs at 298 and 323
start the post-restart client sessions. Authentication/registration control
objects are encrypted within TLS application traffic; their JSON/passwords are
not visible in the capture. TCP handshake evidence is distinct from app login.

The demo intentionally suppresses one server transport ACK. Frames **101** and
**112** contain byte-identical DATA with packet ID
`b0c7d284-a338-4a2e-83c2-89ba12b2406e`, sequence 0, followed by its ACK at **113**:

```text
udp.payload[10:16] == b0:c7:d2:84:a3:38:4a:2e:83:c2:89:ba:12:b2:40:6e
```

This is application UDP retransmission; Wireshark's `tcp.analysis.retransmission`
filter does not detect it. The application demo also checks delivery and SHA-256;
those logs accompany the real trace, not replace it.

The 32 KiB file uses stream `cdef6e7a-1b08-44e3-aeb2-146af6011975`, visible across
many DATA/ACK packets from frame 114 onward:

```text
udp.payload[26:16] == cd:ef:6e:7a:1b:08:44:e3:ae:b2:14:6a:f6:01:19:75
```

Header offsets relative to the UDP payload: magic 0..3, version 4, kind 5,
sequence 6..9, packet UUID 10..25, stream UUID 26..41. DATA then has a 12-byte
nonce and encrypted metadata/binary plus a 16-byte GCM tag. ACK has exactly
42 payload bytes (`udp.length == 50` includes the 8-byte UDP header).
Maximum UDP payload is 1200; file chunks carry at most 800 raw bytes.
Visible headers/ciphertext and absence of readable chat text are observations;
AES-GCM correctness is additionally checked by the crypto/tamper tests.

## Repeat on Windows / Npcap

Install Wireshark with Npcap loopback support if absent. Close other assignment
server processes so 9100/9101 are free. Generate the localhost certificate using
README setup; the demo verifies that certificate and does not alter OS trust.
List interfaces, then capture loopback in terminal 1:

```powershell
& 'C:\Program Files\Wireshark\dumpcap.exe' -D
& 'C:\Program Files\Wireshark\dumpcap.exe' -i '\Device\NPF_Loopback' -f 'tcp port 9100 or udp port 9101' -a duration:30 -w demo.pcapng
```

While capture is active, run terminal 2:

```powershell
.\.venv\Scripts\python.exe -m scripts.wireshark_demo
```

The demo creates temporary accounts, verifies TLS, sends encrypted chat, suppresses
one ACK, transfers a Unicode-named binary file, verifies SHA-256 receipt, stops
the server, starts it again and reauthenticates before replaying a pending chat.
The printed packet/stream IDs differ on every run; use that run's values when filtering.

## Repeat on Linux

Use Wireshark/TShark from your distribution and capture `lo` for localhost, or
the actual LAN interface for separate machines. With capture permissions set:

```bash
sudo dumpcap -i lo -f 'tcp port 9100 or udp port 9101' -a duration:30 -w demo.pcapng
# In another terminal, while the capture is active:
.venv/bin/python -m scripts.wireshark_demo
```

## Team checklist

- [ ] Show SYN/SYN-ACK and TLS handshake/application records on TCP 9100.
- [ ] Identify UDP DATA/ACK by the actual header bytes and stream UUID.
- [ ] Show file data spanning many sequences and a receiver SHA-256 receipt.
- [ ] Show repeated packet UUID after intentional ACK loss.
- [ ] Show FIN/RST/closure followed by new TCP/TLS sessions after restart.
- [ ] Inspect ciphertext without exporting keys or claiming plaintext authentication is visible.
- [ ] Repeat on Ubuntu/LAN if new cross-machine capture evidence is required.

Fixed-window flow limiting is not BBR/CUBIC congestion control. See protocol.md
for the actual constants and the remaining assignment interpretation gap.
