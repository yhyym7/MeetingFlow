"""Password hashing shared by initialization and the future login service."""

import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    if not password or len(password) > 256:
        raise ValueError("Password must contain 1 to 256 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=32768, r=8, p=3,
        maxmem=64 * 1024 * 1024, dklen=32,
    )
    return f"scrypt$32768$8$3${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    if not password or len(password) > 256:
        return False
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if (algorithm, n, r, p) != ("scrypt", "32768", "8", "3"):
            return False
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if len(salt) != 16 or len(expected) != 32:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=32768, r=8, p=3,
            maxmem=64 * 1024 * 1024, dklen=32,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
