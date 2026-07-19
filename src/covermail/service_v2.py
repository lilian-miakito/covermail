"""Context-bound encryption service for cm-arithmetic-v2."""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import Address, validate_address
from covermail.crypto.hpke import decrypt_inner_v2, encrypt_inner_v2
from covermail.errors import OuterFrameError
from covermail.protocol.inner_frame import pack_inner, unpack_inner
from covermail.protocol.v2_frame import pack_v2_stream, unpack_v2_stream


def _validated_v2_address(address: Address) -> Address:
    validated = validate_address(address)
    if validated["codec"]["id"] != "cm-arithmetic-v2":
        raise OuterFrameError("context-bound v2 service requires cm-arithmetic-v2")
    return validated


def encrypt_message_v2(address: Address, secret: str, subject: str, primer: str) -> bytes:
    validated = _validated_v2_address(address)
    inner = pack_inner(secret)
    hpke_blob = encrypt_inner_v2(validated, inner, subject, primer)
    return pack_v2_stream(validated, hpke_blob, subject, primer)


def decrypt_message_v2(
    address: Address,
    private_key: x25519.X25519PrivateKey,
    stream: bytes,
    subject: str,
    primer: str,
) -> tuple[bytes, str]:
    validated = _validated_v2_address(address)
    hpke_blob = unpack_v2_stream(validated, stream, subject, primer)
    inner = decrypt_inner_v2(validated, private_key, hpke_blob, subject, primer)
    return unpack_inner(inner)
