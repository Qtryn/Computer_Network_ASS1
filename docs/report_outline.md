# Suggested PDF report outline (keep it short)

The handout specifically asks for a **Technical Explanation Report (PDF)**.
This Markdown is just a writing outline, **not** the PDF submission.

1. **Title / Team** — course, assignment title, 5 members and individual roles
   (confirm the teacher permits five members).
2. **System Architecture** (Member 1) — one architecture diagram from
   `docs/architecture.md`; explain TCP control, UDP data, local HTTP UI.
3. **Custom Protocol** (Member 1 + Member 2) — UDP header table and application message
   types in `docs/protocol.md`; describe sequence, ACK, timeout, retransmission,
   stream IDs and 800-byte file chunks.
4. **Chat and File Transfer** (Member 3) — one chat sequence and one file sequence;
   include SHA-256 verification and evidence from real files.
5. **UI and Security** (Member 4 + Member 5) — screenshot of online users, chat, file
   progress, and a short note on AES-GCM and key distribution.
6. **Testing Results** (Member 5) — table of test name, procedure, expected and actual
   result; 2-client smoke, 20-client stress, lost packet/ordering, broken client.
7. **Challenges & Solutions (~1 page)** (all members) — describe actual issues
   and fixes. Example discovered during development: stale user-list updates
   due to overlapping login broadcasts, fixed by monotonically increasing
   user-list `version` numbers. Include only challenges genuinely observed.

Keep report claims consistent with `docs/rubric_checklist.md`. Do not state
BBR/CUBIC, end-to-end encrypted authentication or production-grade security
exists unless the team has actually implemented and tested it.
