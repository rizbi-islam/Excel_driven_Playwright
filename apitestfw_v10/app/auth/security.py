"""
app/auth/security.py — Password hashing (SHA-256 + random salt).
No external deps required.
"""
import hashlib
import os


def hash_password(plain: str) -> str:
    """Returns 'salt:hash' string for storage."""
    salt = os.urandom(16).hex()
    h    = hashlib.sha256(f"{salt}{plain}".encode()).hexdigest()
    return f"{salt}:{h}"


def verify_password(plain: str, stored: str) -> bool:
    """Verify a plaintext password against a stored 'salt:hash'."""
    try:
        salt, h = stored.split(":", 1)
        return hashlib.sha256(f"{salt}{plain}".encode()).hexdigest() == h
    except Exception:
        return False
