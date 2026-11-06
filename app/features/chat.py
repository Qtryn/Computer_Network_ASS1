"""Member 3: chat rules; independent from socket and UI implementations."""
from app.common.config import MAX_CHAT_BYTES, MAX_DATAGRAM
from app.common.protocol import HEADER, encode_message
from app.security.crypto import OVERHEAD


class ChatService:
    @staticmethod
    def build_message(sender, recipient, text):
        """Recipient '*' means broadcast; otherwise a private username."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Cannot send an empty message")
        if len(text.encode("utf-8")) > MAX_CHAT_BYTES:
            raise ValueError(f"Message exceeds {MAX_CHAT_BYTES} UTF-8 bytes")
        if not isinstance(recipient, str) or not recipient.strip():
            raise ValueError("Recipient is required")
        message = {"type": "CHAT", "sender": sender, "recipient": recipient, "text": text}
        # The client adds a 48-character token (registry's token_hex(24)).
        # Encode it too so JSON escaping and all metadata count toward the limit.
        encoded = encode_message({**message, "token": "0" * 48})
        if HEADER.size + OVERHEAD + len(encoded) > MAX_DATAGRAM:
            raise ValueError(f"Encoded message exceeds {MAX_DATAGRAM}-byte UDP datagram limit")
        return message

    @staticmethod
    def recipients(sender, recipient, online_users):
        """Server-side routing: do not broadcast private messages."""
        online = set(online_users)
        if sender not in online:
            raise ValueError("Sender is not online")
        if recipient == "*":
            return [user for user in sorted(online) if user != sender]
        if recipient not in online:
            raise ValueError(f"Recipient '{recipient}' is offline")
        if recipient == sender:
            return [sender]  # A self-message is allowed.
        return [recipient]
