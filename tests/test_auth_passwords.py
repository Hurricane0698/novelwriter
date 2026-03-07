from __future__ import annotations

import bcrypt

from app.core.auth import hash_password, verify_password


def test_pbkdf2_hash_and_verify_roundtrip():
    hashed = hash_password("devtest123")
    assert verify_password("devtest123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_legacy_bcrypt_verify_fallback():
    pw = "devtest123"
    hashed = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    assert hashed.startswith("$2")
    assert verify_password(pw, hashed) is True
    assert verify_password("wrong", hashed) is False

