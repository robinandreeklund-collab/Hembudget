from __future__ import annotations

import base64
import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type, hash_secret_raw


ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536   # 64 MB
ARGON2_PARALLELISM = 2


def _load_or_create_salt(salt_path) -> bytes:
    from ..config import settings

    p = salt_path or (settings.data_dir / "master.salt")
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return p.read_bytes()
    salt = os.urandom(16)
    p.write_bytes(salt)
    return salt


def derive_key(password: str, *, salt: bytes | None = None) -> str:
    """Derive a hex key for SQLCipher from the user's password using Argon2id."""
    from ..config import settings

    salt = salt or _load_or_create_salt(settings.data_dir / "master.salt")
    raw = hash_secret_raw(
        password.encode("utf-8"),
        salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=32,
        type=Type.ID,
    )
    # SQLCipher accepts a hex key with "x'...'" syntax
    return raw.hex()


_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except VerifyMismatchError:
        return False


def random_token(n: int = 32) -> str:
    return base64.urlsafe_b64encode(os.urandom(n)).decode("ascii").rstrip("=")
