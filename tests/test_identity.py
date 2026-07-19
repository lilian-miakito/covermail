from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.canonical import decode_base64url
from covermail.address.fingerprint import machine_address_id
from covermail.crypto.identity import generate_identity, public_key_bytes
from covermail.crypto.private_store import (
    ADDRESS_FILENAME,
    METADATA_FILENAME,
    PRIVATE_KEY_FILENAME,
    load_identity_address,
    save_identity,
    unlock_identity,
)
from covermail.errors import IdentityStorageError, PrivateKeyLockedError


def test_generate_identity_replaces_template_key(address: dict[str, Any]) -> None:
    old_key = address["recipient"]["hpke_public_key"]
    generated, private_key = generate_identity(address)
    assert generated["recipient"]["hpke_public_key"] != old_key
    assert decode_base64url(generated["recipient"]["hpke_public_key"]) == public_key_bytes(
        private_key
    )
    assert address["recipient"]["hpke_public_key"] == old_key


def test_save_and_unlock_identity(
    tmp_path: Path,
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    destination = save_identity(tmp_path / "identities", address, private_key, "correct horse")
    assert destination.name == machine_address_id(address)
    assert load_identity_address(destination) == address
    loaded_address, loaded_key = unlock_identity(destination, "correct horse")
    assert loaded_address == address
    assert public_key_bytes(loaded_key) == public_key_bytes(private_key)

    if os.name == "posix":
        assert destination.stat().st_mode & 0o777 == 0o700
        for name in (ADDRESS_FILENAME, PRIVATE_KEY_FILENAME, METADATA_FILENAME):
            assert (destination / name).stat().st_mode & 0o777 == 0o600
    assert b"correct horse" not in (destination / PRIVATE_KEY_FILENAME).read_bytes()


def test_wrong_passphrase_is_generic(
    tmp_path: Path,
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    destination = save_identity(tmp_path, address, private_key, "right")
    with pytest.raises(PrivateKeyLockedError, match="could not be unlocked"):
        unlock_identity(destination, "wrong")


def test_private_key_must_match_address(
    tmp_path: Path,
    address: dict[str, Any],
) -> None:
    with pytest.raises(IdentityStorageError, match="does not match"):
        save_identity(tmp_path, address, x25519.X25519PrivateKey.generate(), "passphrase")


def test_identity_is_immutable(
    tmp_path: Path,
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    save_identity(tmp_path, address, private_key, "passphrase")
    with pytest.raises(IdentityStorageError, match="already exists"):
        save_identity(tmp_path, address, private_key, "passphrase")


def test_identity_symlinks_are_rejected(
    tmp_path: Path,
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    destination = save_identity(tmp_path, address, private_key, "passphrase")
    link = tmp_path / "linked"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(IdentityStorageError, match="symlink"):
        load_identity_address(link)


@pytest.mark.parametrize("passphrase", ["", "x" * 1025])
def test_passphrase_limits(
    tmp_path: Path,
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
    passphrase: str,
) -> None:
    with pytest.raises(IdentityStorageError, match="1..1024"):
        save_identity(tmp_path, address, private_key, passphrase)
