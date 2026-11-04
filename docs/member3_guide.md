# Member 3 — Chat and File Transfer

**Scope:** implement application logic, not socket/ACK/retransmission logic.
Member 2 owns reliable UDP; Member 1 owns server/session routing; Member 4 owns
browser UI; Member 5 owns encryption and integration tests.

## 1. Your files

- `app/features/chat.py`: validate a chat message and select recipients.
- `app/features/files.py`: stream file chunks, rebuild files, check SHA-256.
- `tests/test_features.py`: isolated unit tests for your functions.

The `app/client.py` and `app/server/server.py` code already calls your module.
Avoid changing shared message structures without a team decision.

## 2. How chat works

`ChatService.build_message(sender, recipient, text)` creates a valid `CHAT`
message. `recipient="*"` means broadcast; a username means direct message.
`ChatService.recipients(sender, recipient, online_users)` picks destinations.

## 3. How file transfer works

1. `FileSender.prepare(...)` checks a source file, calculates its SHA-256, and
   yields `FILE_START`, multiple `FILE_CHUNK` messages, and `FILE_END`.
2. Member 2 sends those messages over encrypted reliable UDP.
3. Member 1 forwards the messages to the selected receiver.
4. `FileReceiver.process(event)` writes each chunk to a `.part` file, then
   verifies its byte count and SHA-256 before making the final file visible.
5. The receiver sends `FILE_RECEIPT` back to the original sender.

The file is read incrementally, not loaded as one large byte array.
Chunk size is part of `FILE_START` metadata and must not exceed 800 bytes.

## 4. Your first tasks

1. Run `python -m unittest tests.test_features -v`.
2. Read `chat.py`, then `files.py` in that order.
3. Test broadcast, private chat and an offline recipient.
4. Test an empty file, arbitrary binary file, multi-chunk file, and a custom
   smaller chunk size.
5. Verify corrupted file data raises an error and the `.part` file is deleted.
6. Agree with Members 1/2/4 on transfer cancellation and disconnected peers.
7. Write report diagrams for chat and file lifecycle using actual behavior.

**Avoid adding** message history databases, group channels, cloud storage,
video calls, emojis or other features not in the assignment.

## 5. Git commands (example)

```bash
git switch main
git pull origin main
git switch -c feature/member3-chat-file
# edit your files and run tests
git add app/features/ tests/test_features.py
git commit -m "Implement chat and file handling"
git push -u origin feature/member3-chat-file
```

Open a Pull Request and request review. Do not push directly to `main`.
