"""Member 1: thread-safe session registry; one online session per username."""
import re
import secrets
import threading
from dataclasses import dataclass


@dataclass
class Session:
    username: str
    token: str
    ip: str
    udp_port: int
    control_socket: object

    @property
    def udp_addr(self):
        return (self.ip, self.udp_port)


class UserRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._users = {}
        self._version = 0

    def login(self, username, ip, port, control_socket):
        if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,20}", username):
            raise ValueError("Username: 1-20 letters, digits or underscores")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValueError("Invalid UDP port")
        with self._lock:
            if username in self._users:
                raise ValueError("Username already online")
            session = Session(username, secrets.token_hex(24), ip, port, control_socket)
            self._users[username] = session
            self._version += 1
            return session

    def logout(self, username, token):
        with self._lock:
            existing = self._users.get(username)
            if existing and existing.token == token:
                del self._users[username]
                self._version += 1
                return True
            return False

    def get(self, username):
        with self._lock:
            return self._users.get(username)

    def names(self):
        with self._lock:
            return sorted(self._users)

    def snapshot(self):
        """Atomic roster plus revision so late updates cannot overwrite new ones."""
        with self._lock:
            return self._version, sorted(self._users)

    def all_sessions(self):
        with self._lock:
            return list(self._users.values())

    def authenticate(self, username, token, udp_addr):
        with self._lock:
            session = self._users.get(username)
            if session and session.token == token and session.udp_addr == udp_addr:
                return session
            return None
