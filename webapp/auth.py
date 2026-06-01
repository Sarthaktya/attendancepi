import os
import uuid
from fastapi import Request

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
PI_SECRET      = os.getenv("PI_SECRET",      "pisecret123")

_sessions: set[str] = set()


def create_session() -> str:
    token = str(uuid.uuid4())
    _sessions.add(token)
    return token


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get("session")
    return token is not None and token in _sessions
