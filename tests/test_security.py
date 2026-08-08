"""Unit tests for password hashing and JWT."""
import pytest
from jose import jwt, JWTError
from datetime import datetime, timezone, timedelta

try:
    import bcrypt
    HAS_BCRYPT = True
except Exception:
    HAS_BCRYPT = False


def test_password_hash_roundtrip():
    """Password hashing should verify correctly."""
    if not HAS_BCRYPT:
        pytest.skip("bcrypt package is not installed")
    pw = b"test_password"
    h1 = bcrypt.hashpw(pw, bcrypt.gensalt())
    h2 = bcrypt.hashpw(pw, bcrypt.gensalt())
    assert h1 != h2
    assert bcrypt.checkpw(pw, h1)
    assert bcrypt.checkpw(pw, h2)
    assert not bcrypt.checkpw(b"wrong", h1)


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
