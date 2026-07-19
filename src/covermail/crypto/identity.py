"""X25519 recipient identity generation and address binding."""

from __future__ import annotations

import copy

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.canonical import encode_base64url
from covermail.address.schema import Address, validate_address


def generate_identity(address_template: object) -> tuple[Address, x25519.X25519PrivateKey]:
    """Generate a fresh key and replace only the template's public-key field."""
    if not isinstance(address_template, dict):
        raise TypeError("address template must be an object")
    address = copy.deepcopy(address_template)
    recipient = address.get("recipient")
    if not isinstance(recipient, dict):
        raise TypeError("address template recipient must be an object")

    private_key = x25519.X25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    recipient["hpke_public_key"] = encode_base64url(public_raw)
    return validate_address(address), private_key


def public_key_bytes(private_key: x25519.X25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
