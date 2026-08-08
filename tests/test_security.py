"""Unit tests for password hashing and JWT."""
import pytest
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timezone, timedelta


def test_password_hash_roundtrip():
    """Password hashing should verify correctly."""
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    pw = "test_password"  # <=72 bytes for bcrypt compatibility
    h1 = ctx.hash(pw)
    h2 = ctx.hash(pw)
    assert h1 != h2  # salt makes hashes unique
    assert ctx.verify(pw, h1)
    assert ctx.verify(pw, h2)
    assert not ctx.verify("wrong", h1)


def test_jwt_payload_structure():
    """JWT encode/decode roundtrip."""
    secret = "test_secret_key_for_unit_tests_only"
    payload = {"sub": "user123", "role": "admin"}
    token = jwt.encode(payload, secret, algorithm="HS256")
    decoded = jwt.decode(token, secret, algorithms=["HS256"])
    assert decoded["sub"] == "user123"
    assert decoded["role"] == "admin"


def test_jwt_expiry():
    """Expired tokens should raise."""
    secret = "test_secret_key_for_unit_tests_only"
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {"sub": "user", "exp": past}
    token = jwt.encode(payload, secret, algorithm="HS256")
    with pytest.raises(JWTError):
        jwt.decode(token, secret, algorithms=["HS256"])
