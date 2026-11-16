"""Session-pair capabilities issued to authenticated peers over TLS."""
import hashlib
import hmac
import uuid

from app.common.protocol import encode_message


def pair_key(secret, first, second):
    return hmac.digest(secret, ":".join(sorted((first, second))).encode("ascii"), "sha256")


def peer_stream(key, sender, kind):
    return uuid.UUID(bytes=hmac.digest(key, f"{sender}:{kind}".encode("ascii"), "sha256")[:16])


def signed(message, key):
    return {**message, "proof": hmac.new(key, encode_message(message), hashlib.sha256).hexdigest()}


def authenticated(message, key):
    proof = message.get("proof")
    if not isinstance(proof, str) or not proof.isascii():
        return False
    body = {name: value for name, value in message.items() if name != "proof"}
    return hmac.compare_digest(signed(body, key)["proof"], proof)
