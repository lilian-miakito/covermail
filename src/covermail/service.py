"""Context-bound Covermail message encryption service."""

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import Address, validate_address
from covermail.crypto.hpke import decrypt_inner, encrypt_inner
from covermail.protocol.inner_frame import pack_inner, unpack_inner
from covermail.protocol.stego_stream import pack_stream, unpack_stream


def encrypt_message(address: Address, secret: str, subject: str, primer: str) -> bytes:
    validated = validate_address(address)
    inner = pack_inner(secret)
    hpke_blob = encrypt_inner(validated, inner, subject, primer)
    return pack_stream(validated, hpke_blob, subject, primer)


def decrypt_message(
    address: Address,
    private_key: x25519.X25519PrivateKey,
    stream: bytes,
    subject: str,
    primer: str,
) -> tuple[bytes, str]:
    validated = validate_address(address)
    hpke_blob = unpack_stream(validated, stream, subject, primer)
    inner = decrypt_inner(validated, private_key, hpke_blob, subject, primer)
    return unpack_inner(inner)
