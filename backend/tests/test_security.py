import pytest

from app.security import hash_password, verify_password


def test_hash_is_salted_and_verifies_unicode_password():
    password = "演示密码-OnlyForTest42"
    first, second = hash_password(password), hash_password(password)
    assert first != second
    assert password not in first
    assert verify_password(password, first)
    assert not verify_password("wrong-password", first)


@pytest.mark.parametrize("encoded", ["", "plaintext", "scrypt$1$8$3$ff$ff", "scrypt$32768$8$3$xx$xx"])
def test_malformed_hash_is_rejected(encoded):
    assert not verify_password("some-password", encoded)
