"""Member 3: chat rules; independent from socket and UI implementations."""
from app.common.config import MAX_CHAT_BYTES


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
        return {"type": "CHAT", "sender": sender, "recipient": recipient, "text": text}

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
