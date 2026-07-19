"""Encrypted PKCS#8 identity storage with strict POSIX permissions."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.canonical import canonical_json, read_address_file
from covermail.address.fingerprint import machine_address_id
from covermail.address.schema import Address, validate_address
from covermail.crypto.identity import public_key_bytes
from covermail.errors import IdentityStorageError, PrivateKeyLockedError

ADDRESS_FILENAME = "address.json"
PRIVATE_KEY_FILENAME = "private-key.pem"
METADATA_FILENAME = "metadata.json"
MAX_PRIVATE_KEY_BYTES = 16384


def _passphrase_bytes(passphrase: str) -> bytes:
    try:
        encoded = passphrase.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise IdentityStorageError("passphrase is not valid Unicode") from error
    if not 1 <= len(encoded) <= 1024:
        raise IdentityStorageError("passphrase byte length must be 1..1024")
    return encoded


def serialize_private_key(
    private_key: x25519.X25519PrivateKey,
    passphrase: str,
) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(_passphrase_bytes(passphrase)),
    )


def deserialize_private_key(pem: bytes, passphrase: str) -> x25519.X25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(pem, password=_passphrase_bytes(passphrase))
    except (TypeError, ValueError) as error:
        raise PrivateKeyLockedError("private identity could not be unlocked") from error
    if not isinstance(key, x25519.X25519PrivateKey):
        raise PrivateKeyLockedError("private identity has an unexpected key type")
    return key


def _write_private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        with suppress(OSError):
            os.close(descriptor)
        raise


def save_identity(
    identities_dir: Path,
    address: Address,
    private_key: x25519.X25519PrivateKey,
    passphrase: str,
) -> Path:
    """Atomically create one immutable private identity directory."""
    validate_address(address)
    expected_public = public_key_bytes(private_key)
    recipient = address["recipient"]
    if not isinstance(recipient, dict) or not isinstance(recipient.get("hpke_public_key"), str):
        raise IdentityStorageError("validated address has no public key")
    from covermail.address.canonical import decode_base64url

    if decode_base64url(recipient["hpke_public_key"]) != expected_public:
        raise IdentityStorageError("private key does not match public address")

    identities_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        identities_dir.chmod(0o700)
    identity_id = machine_address_id(address)
    destination = identities_dir / identity_id
    if destination.exists():
        raise IdentityStorageError("identity already exists")

    temporary = Path(tempfile.mkdtemp(prefix=f".{identity_id}.", dir=identities_dir))
    try:
        temporary.chmod(0o700)
        _write_private_file(temporary / ADDRESS_FILENAME, canonical_json(address) + b"\n")
        _write_private_file(
            temporary / PRIVATE_KEY_FILENAME,
            serialize_private_key(private_key, passphrase),
        )
        metadata = {
            "format": "covermail-identity-metadata",
            "version": 1,
            "address_id": identity_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        _write_private_file(
            temporary / METADATA_FILENAME,
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
        )
        temporary.rename(destination)
    except Exception as error:
        for child in temporary.iterdir():
            child.unlink(missing_ok=True)
        temporary.rmdir()
        if isinstance(error, IdentityStorageError):
            raise
        raise IdentityStorageError("private identity could not be stored") from error
    return destination


def load_identity_address(identity_dir: Path) -> Address:
    if identity_dir.is_symlink():
        raise IdentityStorageError("identity directory must not be a symlink")
    address_path = identity_dir / ADDRESS_FILENAME
    if address_path.is_symlink():
        raise IdentityStorageError("identity address must not be a symlink")
    address = validate_address(read_address_file(address_path))
    if identity_dir.name != machine_address_id(address):
        raise IdentityStorageError("identity directory does not match its address")
    return address


def unlock_identity(
    identity_dir: Path,
    passphrase: str,
) -> tuple[Address, x25519.X25519PrivateKey]:
    address = load_identity_address(identity_dir)
    key_path = identity_dir / PRIVATE_KEY_FILENAME
    if key_path.is_symlink():
        raise IdentityStorageError("encrypted private key must not be a symlink")
    try:
        with key_path.open("rb") as stream:
            pem = stream.read(MAX_PRIVATE_KEY_BYTES + 1)
    except OSError as error:
        raise IdentityStorageError("encrypted private key could not be read") from error
    if len(pem) > MAX_PRIVATE_KEY_BYTES:
        raise IdentityStorageError("encrypted private key exceeds local limit")
    key = deserialize_private_key(pem, passphrase)
    recipient = address["recipient"]
    from covermail.address.canonical import decode_base64url

    if not isinstance(recipient, dict) or not isinstance(recipient.get("hpke_public_key"), str):
        raise IdentityStorageError("validated address has no public key")
    if public_key_bytes(key) != decode_base64url(recipient["hpke_public_key"]):
        raise PrivateKeyLockedError("private identity does not match its address")
    return address, key
