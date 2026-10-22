"""Accounts, password hashing and sign-in sessions.

Passwords are hashed with scrypt from the standard library (no extra dependency). Sessions are random
bearer tokens; the database stores only their SHA-256 digest. Repeated failed sign-ins for one username
are throttled in memory, which is enough for a single backend process.
"""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ConflictError, InvalidInputError, ItemNotFoundError
from app.models.user import User, UserRole, UserSession

SESSION_HOURS = 12
MIN_PASSWORD_LENGTH = 10
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
_FAIL_WINDOW_S, _FAIL_LIMIT = 15 * 60, 5

# What each role may change. Every signed-in user may read everything.
PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.ADMIN: frozenset({"inventory", "transfers", "receiving", "procurement", "inspect", "hold", "users"}),
    UserRole.STOREKEEPER: frozenset({"inventory", "transfers", "receiving", "hold"}),
    UserRole.PROCUREMENT: frozenset({"procurement"}),
    UserRole.INSPECTOR: frozenset({"inspect", "hold"}),
    UserRole.VIEWER: frozenset(),
}


def permissions_of(role: UserRole) -> list[str]:
    return sorted(PERMISSIONS[role])


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, maxmem=64 * 1024 * 1024, **_SCRYPT)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected), maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def check_password_rules(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidInputError(f"The password must be at least {MIN_PASSWORD_LENGTH} characters long")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- throttling -------------------------------------------------------------------------------------
_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def _recent_failures(username: str, now: float) -> list[float]:
    times = [t for t in _failures.get(username, []) if now - t < _FAIL_WINDOW_S]
    _failures[username] = times
    return times


def reset_throttle() -> None:
    with _lock:
        _failures.clear()


class TooManyAttempts(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


# ---- accounts -------------------------------------------------------------------------------------------
def normalise_username(username: str) -> str:
    return username.strip().lower()


def create_user(db: Session, username: str, display_name: str, role: UserRole, password: str,
                email: str | None = None) -> User:
    username = normalise_username(username)
    check_password_rules(password)
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise ConflictError(f"The username {username!r} is already taken")
    user = User(username=username, display_name=display_name.strip(), email=email, role=role,
                password_hash=hash_password(password), is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ItemNotFoundError("User", user_id)
    return user


def active_admins(db: Session, excluding: int | None = None) -> int:
    query = select(func.count()).select_from(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
    if excluding is not None:
        query = query.where(User.id != excluding)
    return db.scalar(query)


def update_user(db: Session, user_id: int, *, display_name=None, email=None, role=None, is_active=None,
                acting_user: User) -> User:
    user = get_user(db, user_id)
    losing_admin = user.role == UserRole.ADMIN and ((role is not None and role != UserRole.ADMIN) or is_active is False)
    if losing_admin and not active_admins(db, excluding=user.id):
        raise ConflictError("This is the last active admin; make another user an admin first")
    if user.id == acting_user.id and is_active is False:
        raise ConflictError("You cannot deactivate your own account")
    if display_name is not None:
        user.display_name = display_name.strip()
    if email is not None:
        user.email = email or None
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            revoke_all_sessions(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: User, new_password: str, *, end_other_sessions: bool = True) -> None:
    check_password_rules(new_password)
    user.password_hash = hash_password(new_password)
    if end_other_sessions:
        revoke_all_sessions(db, user.id)
    db.commit()


# ---- sessions -------------------------------------------------------------------------------------------
def login(db: Session, username: str, password: str) -> tuple[str, User, datetime]:
    """Returns (token, user, expires_at). Raises InvalidInputError on bad credentials, TooManyAttempts when throttled."""
    key = normalise_username(username)
    now = time.monotonic()
    with _lock:
        failures = _recent_failures(key, now)
        if len(failures) >= _FAIL_LIMIT:
            raise TooManyAttempts(int(_FAIL_WINDOW_S - (now - failures[0])) + 1)
    user = db.scalar(select(User).where(User.username == key))
    # Hash even when the user does not exist so response time does not reveal valid usernames.
    ok = verify_password(password, user.password_hash if user else hash_password("not-a-real-password"))
    if not user or not ok or not user.is_active:
        with _lock:
            _failures.setdefault(key, []).append(now)
        raise InvalidInputError("Incorrect username or password, or the account is disabled")
    with _lock:
        _failures.pop(key, None)
    token = secrets.token_urlsafe(32)
    created = datetime.now()
    expires = created + timedelta(hours=SESSION_HOURS)
    db.add(UserSession(token_hash=_token_hash(token), user_id=user.id, created_at=created, expires_at=expires))
    user.last_login_at = created
    db.commit()
    return token, user, expires


def user_for_token(db: Session, token: str) -> User | None:
    session = db.get(UserSession, _token_hash(token))
    if session is None or session.revoked_at is not None or session.expires_at <= datetime.now():
        return None
    user = session.user
    return user if user and user.is_active else None


def logout(db: Session, token: str) -> None:
    session = db.get(UserSession, _token_hash(token))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now()
        db.commit()


def revoke_all_sessions(db: Session, user_id: int) -> None:
    now = datetime.now()
    for session in db.scalars(select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))):
        session.revoked_at = now
