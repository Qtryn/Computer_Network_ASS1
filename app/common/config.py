"""Shared settings; override ports/host through command-line arguments."""

TCP_PORT = 9100
UDP_PORT = 9101
MAX_DATAGRAM = 1200  # Keep UDP datagrams below the usual Ethernet MTU.
FILE_CHUNK_SIZE = 800
WINDOW_SIZE = 4
ACK_TIMEOUT = 0.35
MAX_RETRIES = 10
MAX_CHAT_BYTES = 600
MAX_FILE_NAME = 100
PROTOCOL_VERSION = 1

