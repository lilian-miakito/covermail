"""Prefix-bound single-capsule Covermail packet service."""

import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import Address, validate_address
from covermail.crypto.hpke import (
    HPKE_ENCAPSULATED_KEY_BYTES,
    HPKE_TAG_BYTES,
    decrypt_capsule,
    encrypt_capsule,
)
from covermail.protocol.inner_frame import pack_inner, unpack_inner
from covermail.protocol.packet import (
    pack_header,
    validate_packet,
)


@dataclass(frozen=True, slots=True)
class EncryptedPacket:
    header: bytes
    capsule: bytes


def encrypt_message(
    address: Address,
    secret: str,
    prefix_token_ids: tuple[int, ...],
) -> EncryptedPacket:
    validated = validate_address(address)
    inner = pack_inner(secret)
    capsule_bytes = HPKE_ENCAPSULATED_KEY_BYTES + len(inner) + HPKE_TAG_BYTES
    header = pack_header(capsule_bytes)
    capsule = encrypt_capsule(validated, inner, prefix_token_ids, header)
    if len(capsule) != capsule_bytes:
        raise AssertionError("HPKE capsule has an unexpected length")
    return EncryptedPacket(header, capsule)


def decrypt_message(
    address: Address,
    private_key: x25519.X25519PrivateKey,
    packet: EncryptedPacket,
    prefix_token_ids: tuple[int, ...],
) -> tuple[bytes, str]:
    validated = validate_address(address)
    validate_packet(packet.header, packet.capsule)
    inner = decrypt_capsule(
        validated,
        private_key,
        packet.capsule,
        prefix_token_ids,
        packet.header,
    )
    message_id = hashlib.sha256(packet.capsule).digest()[:16]
    return message_id, unpack_inner(inner)
