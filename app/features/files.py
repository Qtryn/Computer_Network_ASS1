"""Member 3: file metadata, chunking, streaming reassembly and SHA-256 verification.

No socket code here: sender produces application messages; receiver consumes them.
"""
import hashlib
import math
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.common.config import FILE_CHUNK_SIZE, MAX_FILE_NAME


def safe_filename(filename):
    """Reject path traversal and unsupported characters in names received over wire."""
    name = str(filename).replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.() -]", "_", name, flags=re.UNICODE).strip(" .")
    if not name or name in (".", ".."):
        name = "received_file"
    # Windows treats these special device names as invalid filenames.
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    if name.split(".")[0].upper() in reserved:
        name = "_" + name
    return name[:MAX_FILE_NAME]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class FileSender:
    def __init__(self, chunk_size=FILE_CHUNK_SIZE):
        if chunk_size <= 0 or chunk_size > FILE_CHUNK_SIZE:
            raise ValueError(f"chunk_size must be within 1..{FILE_CHUNK_SIZE}")
        self.chunk_size = chunk_size

    def prepare(self, path, sender, recipient, display_name=None):
        """Return (file_id, total_packet_count, message iterator).

        The iterator reads one chunk at a time; it does not load files into RAM.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        if recipient == "*" or not recipient:
            raise ValueError("File transfer requires a specific recipient")
        size = path.stat().st_size
        digest = sha256_file(path)
        file_id = str(uuid.uuid4())
        total_chunks = math.ceil(size / self.chunk_size)

        def packets():
            basic = {"file_id": file_id, "sender": sender, "recipient": recipient}
            yield {**basic, "type": "FILE_START", "name": safe_filename(display_name or path.name),
                   "size": size, "total_chunks": total_chunks,
                   "chunk_size": self.chunk_size, "sha256": digest}
            with path.open("rb") as file:
                for index in range(total_chunks):
                    data = file.read(self.chunk_size)
                    if not data:
                        raise OSError("Source file changed while transmitting")
                    yield {**basic, "type": "FILE_CHUNK", "index": index, "data": data}
                if file.read(1):
                    raise OSError("Source file grew while transmitting")
            yield {**basic, "type": "FILE_END"}

        return file_id, total_chunks + 2, packets()


@dataclass
class ReceivingFile:
    name: str
    expected_size: int
    expected_chunks: int
    chunk_size: int
    digest: str
    temp_path: Path
    handle: object
    next_chunk: int = 0
    bytes_written: int = 0


class FileReceiver:
    def __init__(self, download_dir):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.incoming = {}

    def process(self, event):
        """Consume a file event, return a progress/complete event (or None).

        On any error the current temporary file is removed, never marked complete.
        """
        kind = event.get("type")
        file_id = event.get("file_id")
        if not isinstance(file_id, str):
            raise ValueError("Missing file ID")
        try:
            if kind == "FILE_START":
                if file_id in self.incoming:
                    raise ValueError("Duplicate FILE_START")
                uuid.UUID(file_id)  # Ensure file_id is a safe, stable identifier.
                size = int(event["size"])
                total = int(event["total_chunks"])
                chunk_size = int(event["chunk_size"])
                if not 1 <= chunk_size <= FILE_CHUNK_SIZE:
                    raise ValueError("Invalid chunk size")
                if size < 0 or total != math.ceil(size / chunk_size):
                    raise ValueError("Invalid file size/chunk count")
                digest = str(event["sha256"])
                if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError("Invalid SHA-256 hash")
                name = safe_filename(event["name"])
                temp_path = self.download_dir / f".{file_id}.part"
                handle = open(temp_path, "wb")
                self.incoming[file_id] = ReceivingFile(name, size, total, chunk_size, digest, temp_path, handle)
                return {"type": "FILE_PROGRESS", "file_id": file_id, "name": name,
                        "sender": event.get("sender"), "percent": 0}

            current = self.incoming.get(file_id)
            if current is None:
                raise ValueError("Received file data before FILE_START")
            if kind == "FILE_CHUNK":
                if event.get("index") != current.next_chunk:
                    raise ValueError("File chunks arrived out of order")
                data = event.get("data", b"")
                if not isinstance(data, bytes) or len(data) > current.chunk_size or not data:
                    raise ValueError("Invalid file chunk")
                if current.bytes_written + len(data) > current.expected_size:
                    raise ValueError("File exceeds declared size")
                current.handle.write(data)
                current.bytes_written += len(data)
                current.next_chunk += 1
                percent = round(100 * current.bytes_written / max(1, current.expected_size))
                return {"type": "FILE_PROGRESS", "file_id": file_id, "name": current.name,
                        "sender": event.get("sender"), "percent": percent}
            if kind == "FILE_END":
                current.handle.close()
                if current.next_chunk != current.expected_chunks or current.bytes_written != current.expected_size:
                    raise ValueError("File incomplete")
                if sha256_file(current.temp_path) != current.digest:
                    raise ValueError("SHA-256 mismatch: received file corrupted")
                destination = self.download_dir / current.name
                if destination.exists():
                    stem, suffix = destination.stem, destination.suffix
                    for counter in range(1, 10000):
                        candidate = self.download_dir / f"{stem}_{counter}{suffix}"
                        if not candidate.exists():
                            destination = candidate
                            break
                    else:
                        raise OSError("Too many files with the same name")
                os.replace(current.temp_path, destination)
                del self.incoming[file_id]
                return {"type": "FILE_COMPLETE", "file_id": file_id,
                        "name": destination.name, "path": str(destination),
                        "size": current.expected_size, "sha256": current.digest}
            raise ValueError(f"Unsupported file event: {kind}")
        except Exception:
            self.abort(file_id)
            raise

    def abort(self, file_id):
        current = self.incoming.pop(file_id, None)
        if current:
            if not current.handle.closed:
                current.handle.close()
            current.temp_path.unlink(missing_ok=True)

    def close(self):
        for file_id in list(self.incoming):
            self.abort(file_id)
