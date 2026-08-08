"""Unit tests for app.core.security."""
import pytest

# We test pure functions that don't require full app context
class TestSecurityHelpers:
    def test_imports(self):
        """Security module should import without error."""
        from app.core import security  # noqa: F401

    def test_password_hash_roundtrip(self):
        """Password hashing should be deterministic for same input."""
        from passlib.context import CryptContext
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        pw = "test_password_123"
        h1 = ctx.hash(pw)
        h2 = ctx.hash(pw)
        # Two hashes of same password should differ (salt)
        assert h1 != h2
        # But both should verify
        assert ctx.verify(pw, h1)
        assert ctx.verify(pw, h2)
        # Wrong password should fail
        assert not ctx.verify("wrong", h1)

    def test_jwt_payload_structure(self):
        """JWT encode/decode roundtrip."""
        from jose import jwt
        from datetime import datetime, timezone, timedelta
        secret = "test_secret_key_for_unit_tests_only"
        payload = {"sub": "user123", "role": "admin"}
        token = jwt.encode(payload, secret, algorithm="HS256")
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
        assert decoded["sub"] == "user123"
        assert decoded["role"] == "admin"

    def test_jwt_expiry(self):
        """Expired tokens should raise."""
        from jose import jwt, JWTError
        secret = "test_secret_key_for_unit_tests_only"
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = {"sub": "user", "exp": past}
        token = jwt.encode(payload, secret, algorithm="HS256")
        with pytest.raises(JWTError):
            jwt.decode(token, secret, algorithms=["HS256"])
