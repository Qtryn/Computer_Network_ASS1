"""Small custom UDP framing and application message encoding.

UDP frame: 4-byte magic, version (1), kind (1), sequence (4),
16-byte packet ID, 16-byte stream ID, then AES-GCM ciphertext.
An ACK frame uses the same header and has no payload.
The encrypted message is: 2-byte metadata length + JSON metadata + raw bytes.
"""
import json
import struct
import uuid

from app.common.config import PROTOCOL_VERSION

MAGIC = b"COLB"
DATA = 1
ACK = 2
HEADER = struct.Struct("!4sBBI16s16s")


def encode_frame(kind, packet_id, stream_id, sequence, payload=b""):
    if not 0 <= sequence <= 0xFFFFFFFF:
        raise ValueError("Sequence number out of range")
    return HEADER.pack(MAGIC, PROTOCOL_VERSION, kind, sequence,
                       packet_id.bytes, stream_id.bytes) + payload


def decode_frame(raw):
    if len(raw) < HEADER.size:
        raise ValueError("Truncated UDP frame")
    magic, version, kind, sequence, packet_id, stream_id = HEADER.unpack_from(raw)
    if magic != MAGIC or version != PROTOCOL_VERSION or kind not in (DATA, ACK):
        raise ValueError("Invalid protocol header")
    return kind, uuid.UUID(bytes=packet_id), uuid.UUID(bytes=stream_id), sequence, raw[HEADER.size:]


def encode_message(message):
    """Encode event dict, keeping file-chunk binary data out of JSON/base64."""
    metadata = {k: v for k, v in message.items() if k != "data"}
    binary = message.get("data", b"")
    if not isinstance(binary, bytes):
        raise TypeError("Message 'data' must contain bytes")
    encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 65535:
        raise ValueError("Message metadata too large")
    return struct.pack("!H", len(encoded)) + encoded + binary


def decode_message(payload):
    if len(payload) < 2:
        raise ValueError("Truncated message")
    size = struct.unpack_from("!H", payload)[0]
    if len(payload) < size + 2:
        raise ValueError("Truncated message metadata")
    message = json.loads(payload[2:2 + size].decode("utf-8"))
    if not isinstance(message, dict):
        raise ValueError("Message must be a JSON object")
    if len(payload) > size + 2:
        message["data"] = payload[size + 2:]
    return message
