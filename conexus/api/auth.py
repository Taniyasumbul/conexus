"""Authentication and role-based access.

Roles (each includes the ones before it):
    sales  - create contracts, start negotiations, record customer replies, export redlines
    legal  - + approve / reject escalations, annotate clauses
    admin  - + change the escalation & pricing policy, manage users

Passwords: PBKDF2-HMAC-SHA256 (stdlib), 310k iterations, per-user salt.
Sessions: random 32-byte token in an HttpOnly, SameSite=Lax cookie; only its SHA-256
is stored server-side. API clients may send the same token as `Authorization: Bearer`.

There are no default passwords. The first admin comes from CONEXUS_ADMIN_EMAIL +
CONEXUS_ADMIN_PASSWORD, from `conexus create-user`, or from the one-time setup screen,
which works only while no user exists.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from fastapi import HTTPException, Request

from ..store import Store

ROLES = ("sales", "legal", "admin")
COOKIE = "cnx_session"
SESSION_TTL = 7 * 24 * 3600
ITERATIONS = 310_000
MIN_PASSWORD = 10


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
    return hmac.compare_digest(dk.hex(), digest)


def check_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f"Password must be at least {MIN_PASSWORD} characters")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(store: Store, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    store.create_session(token_hash(token), user_id, time.time() + SESSION_TTL)
    return token


def public_user(u) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"]}


def seed_admin_from_env(store: Store) -> None:
    email, password = os.getenv("CONEXUS_ADMIN_EMAIL"), os.getenv("CONEXUS_ADMIN_PASSWORD")
    if store.user_count() == 0 and email and password:
        store.create_user(email, os.getenv("CONEXUS_ADMIN_NAME", "Administrator"), "admin", hash_password(password))


def _token_from(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE)


def current_user(request: Request) -> dict:
    store: Store = request.app.state.store
    token = _token_from(request)
    u = store.session_user(token_hash(token)) if token else None
    if u is None:
        raise HTTPException(401, "Sign in to continue")
    return public_user(u)


def require(min_role: str):
    """FastAPI dependency: the signed-in user must have at least `min_role`."""
    need = ROLES.index(min_role)

    def dep(request: Request) -> dict:
        user = current_user(request)
        if ROLES.index(user["role"]) < need:
            raise HTTPException(403, f"This needs the {min_role} role. You are signed in as {user['role']}.")
        return user

    return dep
