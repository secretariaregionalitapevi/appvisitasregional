"""Encrypted cookie session backend for stateless deployments."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.sessions.backends.signed_cookies import SessionStore as SignedCookieSessionStore


def _cipher():
    digest = hashlib.sha256(f'ccb-session-v1:{settings.SECRET_KEY}'.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class SessionStore(SignedCookieSessionStore):
    def encode(self, session_dict):
        signed_payload = super().encode(session_dict)
        return _cipher().encrypt(signed_payload.encode()).decode()

    def decode(self, session_data):
        try:
            signed_payload = _cipher().decrypt(session_data.encode()).decode()
        except (InvalidToken, ValueError, TypeError):
            return {}
        return super().decode(signed_payload)
