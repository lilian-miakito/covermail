"""Prefix-bound Covermail metadata and body capsule service."""

from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import Address, validate_address
from covermail.crypto.hpke import (
    BODY_DOMAIN,
    HPKE_ENCAPSULATED_KEY_BYTES,
    HPKE_TAG_BYTES,
    METADATA_DOMAIN,
    decrypt_capsule,
    encrypt_capsule,
)
from covermail.protocol.inner_frame import pack_inner, unpack_inner
from covermail.protocol.packet import (
    METADATA_PLAINTEXT_BYTES,
    PacketMetadata,
    pack_metadata,
    unpack_metadata,
    validate_body,
)

METADATA_CAPSULE_BYTES = HPKE_ENCAPSULATED_KEY_BYTES + METADATA_PLAINTEXT_BYTES + HPKE_TAG_BYTES


@dataclass(frozen=True, slots=True)
class EncryptedPacket:
    metadata: bytes
    body: bytes


def encrypt_message(
    address: Address,
    secret: str,
    prefix_token_ids: tuple[int, ...],
) -> EncryptedPacket:
    validated = validate_address(address)
    inner = pack_inner(secret)
    body = encrypt_capsule(validated, inner, prefix_token_ids, BODY_DOMAIN)
    metadata = encrypt_capsule(
        validated,
        pack_metadata(body),
        prefix_token_ids,
        METADATA_DOMAIN,
    )
    if len(metadata) != METADATA_CAPSULE_BYTES:
        raise AssertionError("metadata HPKE capsule is not fixed length")
    return EncryptedPacket(metadata, body)


def decrypt_metadata(
    address: Address,
    private_key: x25519.X25519PrivateKey,
    metadata_capsule: bytes,
    prefix_token_ids: tuple[int, ...],
) -> PacketMetadata:
    validated = validate_address(address)
    if len(metadata_capsule) != METADATA_CAPSULE_BYTES:
        raise ValueError("metadata capsule has the wrong fixed length")
    plaintext = decrypt_capsule(
        validated,
        private_key,
        metadata_capsule,
        prefix_token_ids,
        METADATA_DOMAIN,
    )
    return unpack_metadata(plaintext)


def decrypt_message(
    address: Address,
    private_key: x25519.X25519PrivateKey,
    packet: EncryptedPacket,
    prefix_token_ids: tuple[int, ...],
) -> tuple[bytes, str]:
    validated = validate_address(address)
    metadata = decrypt_metadata(validated, private_key, packet.metadata, prefix_token_ids)
    validate_body(metadata, packet.body)
    inner = decrypt_capsule(
        validated,
        private_key,
        packet.body,
        prefix_token_ids,
        BODY_DOMAIN,
    )
    return unpack_inner(inner)
