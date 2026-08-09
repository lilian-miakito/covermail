"""The fixed Covermail HPKE Base ciphersuite wrappers."""

import hashlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.hpke import AEAD, KDF, KEM, Suite

from covermail.address.canonical import decode_base64url
from covermail.address.fingerprint import address_digest
from covermail.address.schema import Address
from covermail.errors import DecryptionError

HPKE_INFO_LABEL = b"covermail/hpke-packet\x00"
PREFIX_CONTEXT_LABEL = b"covermail/prefix-context\x00"
HPKE_SUITE = Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.AES_128_GCM)
HPKE_ENCAPSULATED_KEY_BYTES = 32
HPKE_TAG_BYTES = 16


def prefix_context_digest(prefix_token_ids: tuple[int, ...]) -> bytes:
    transcript = bytearray(PREFIX_CONTEXT_LABEL)
    transcript.extend(len(prefix_token_ids).to_bytes(2, "big"))
    for token_id in prefix_token_ids:
        if not 0 <= token_id <= 0xFFFFFFFF:
            raise ValueError("prefix token ID is outside uint32 range")
        transcript.extend(token_id.to_bytes(4, "big"))
    return hashlib.sha256(transcript).digest()


def hpke_info(address: Address, prefix_token_ids: tuple[int, ...], header: bytes) -> bytes:
    if not header:
        raise ValueError("HPKE packet header is empty")
    return (
        HPKE_INFO_LABEL + address_digest(address) + prefix_context_digest(prefix_token_ids) + header
    )


def _public_key(address: Address) -> x25519.X25519PublicKey:
    recipient = address["recipient"]
    if not isinstance(recipient, dict) or not isinstance(recipient.get("hpke_public_key"), str):
        raise TypeError("address must be validated before HPKE use")
    raw = decode_base64url(recipient["hpke_public_key"])
    return x25519.X25519PublicKey.from_public_bytes(raw)


def encrypt_capsule(
    address: Address,
    plaintext: bytes,
    prefix_token_ids: tuple[int, ...],
    header: bytes,
) -> bytes:
    return HPKE_SUITE.encrypt(
        plaintext,
        _public_key(address),
        info=hpke_info(address, prefix_token_ids, header),
    )


def decrypt_capsule(
    address: Address,
    private_key: x25519.X25519PrivateKey,
    capsule: bytes,
    prefix_token_ids: tuple[int, ...],
    header: bytes,
) -> bytes:
    try:
        return HPKE_SUITE.decrypt(
            capsule,
            private_key,
            info=hpke_info(address, prefix_token_ids, header),
        )
    except (InvalidTag, ValueError) as error:
        raise DecryptionError(
            "not an authentic packet for the selected Covermail Address and visible prefix"
        ) from error
