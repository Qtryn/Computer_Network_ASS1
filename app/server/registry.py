"""Member 1: thread-safe session registry; one online session per username."""
import secrets
import threading
import time
from dataclasses import dataclass

from app.server.auth import USERNAME
from app.common.protocol import session_stream


@dataclass(frozen=True)
class Session:
    username: str
    token: str
    ip: str
    udp_port: int
    control_socket: object
    expires_at: float

    @property
    def chat_stream(self):
        return session_stream(self.token)

    @property
    def udp_addr(self):
        return (self.ip, self.udp_port)


class UserRegistry:
    def __init__(self, *, session_seconds=3600, clock=time.monotonic):
        if session_seconds <= 0:
            raise ValueError("Session duration must be positive")
        self._lock = threading.Lock()
        self._users = {}
        self._version = 0
        self._session_seconds = session_seconds
        self._clock = clock

    def _expire_locked(self, now):
        for name in list(self._users):
            self._find_active_locked(name, now)

    def _find_active_locked(self, name, now):
        session = self._users.get(name)
        if session is not None and now >= session.expires_at:
            del self._users[name]
            self._version += 1
            return None
        return session

    def login(self, username, ip, port, control_socket):
        if not isinstance(username, str) or not USERNAME.fullmatch(username):
            raise ValueError("Username: 1-20 letters, digits or underscores")
        if type(port) is not int or not (1 <= port <= 65535):
            raise ValueError("Invalid UDP port")
        with self._lock:
            now = self._clock()
            if self._find_active_locked(username, now) is not None:
                raise ValueError("Username already online")
            session = Session(username, secrets.token_hex(24), ip, port,
                              control_socket, now + self._session_seconds)
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
        if not isinstance(username, str):
            return None
        with self._lock:
            return self._find_active_locked(username, self._clock())

    def names(self):
        return self.snapshot()[1]

    def snapshot(self):
        """Atomic roster plus revision so late updates cannot overwrite new ones."""
        with self._lock:
            self._expire_locked(self._clock())
            return self._version, sorted(self._users)

    def all_sessions(self):
        with self._lock:
            self._expire_locked(self._clock())
            return list(self._users.values())

    def authenticate(self, username, token, udp_addr):
        if not isinstance(username, str) or not isinstance(token, str) or not token.isascii():
            return None
        with self._lock:
            session = self._find_active_locked(username, self._clock())
            if session and session.udp_addr == udp_addr and secrets.compare_digest(session.token, token):
                return session
            return None
