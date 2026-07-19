"""Stage 1 binary Covermail message orchestration."""

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import Address, validate_address
from covermail.crypto.hpke import decrypt_inner, encrypt_inner
from covermail.protocol.inner_frame import pack_inner, unpack_inner
from covermail.protocol.outer_frame import (
    build_outer_payload,
    pack_stego_frame,
    parse_outer_payload,
    unpack_stego_frame,
)


def encrypt_message(address: Address, secret: str) -> bytes:
    validated = validate_address(address)
    inner = pack_inner(secret)
    hpke_blob = encrypt_inner(validated, inner)
    payload = build_outer_payload(validated, hpke_blob)
    return pack_stego_frame(payload)


def decrypt_message(
    address: Address,
    private_key: x25519.X25519PrivateKey,
    frame: bytes,
) -> tuple[bytes, str]:
    validated = validate_address(address)
    payload = unpack_stego_frame(frame)
    hpke_blob = parse_outer_payload(validated, payload)
    inner = decrypt_inner(validated, private_key, hpke_blob)
    return unpack_inner(inner)
