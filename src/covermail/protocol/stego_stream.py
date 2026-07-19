"""Uniformized, context-bound byte stream hidden in a carrier."""

from __future__ import annotations

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from covermail.address.fingerprint import address_digest
from covermail.address.schema import Address
from covermail.crypto.hpke import HPKE_ENCAPSULATED_KEY_BYTES, visible_context_digest
from covermail.errors import OuterFrameError
from covermail.protocol.outer_frame import (
    MAX_STEGO_PAYLOAD_BYTES,
    build_outer_payload,
    parse_outer_payload,
)
from covermail.protocol.varint import decode_uvarint, encode_uvarint

MASK_INFO_LABEL = b"covermail/stego-mask\x00"
MAX_STREAM_BYTES = HPKE_ENCAPSULATED_KEY_BYTES + 3 + MAX_STEGO_PAYLOAD_BYTES


def _xor(left: bytes, right: bytes) -> bytes:
    if len(left) != len(right):
        raise ValueError("XOR inputs differ in length")
    return bytes(first ^ second for first, second in zip(left, right, strict=True))


def _mask(
    address: Address,
    encapsulated_key: bytes,
    subject: str,
    primer: str,
    length: int,
) -> bytes:
    if len(encapsulated_key) != HPKE_ENCAPSULATED_KEY_BYTES:
        raise OuterFrameError("stream has an invalid HPKE encapsulated key")
    if length < 0 or length > MAX_STEGO_PAYLOAD_BYTES + 3:
        raise OuterFrameError("stream mask length exceeds protocol limit")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=address_digest(address),
        info=MASK_INFO_LABEL + visible_context_digest(subject, primer),
    ).derive(encapsulated_key)


def pack_stream(address: Address, hpke_blob: bytes, subject: str, primer: str) -> bytes:
    """Keep HPKE enc first and mask every structured byte that follows."""
    if len(hpke_blob) < HPKE_ENCAPSULATED_KEY_BYTES + 16:
        raise OuterFrameError("HPKE blob is too short")
    encapsulated_key = hpke_blob[:HPKE_ENCAPSULATED_KEY_BYTES]
    ciphertext = hpke_blob[HPKE_ENCAPSULATED_KEY_BYTES:]
    payload = build_outer_payload(address, ciphertext)
    tail = encode_uvarint(len(payload)) + payload
    return encapsulated_key + _xor(
        tail,
        _mask(address, encapsulated_key, subject, primer, len(tail)),
    )


class StreamLengthResolver:
    """Discover a masked stream length after its fixed prefix arrives."""

    def __init__(self, address: Address, subject: str, primer: str) -> None:
        self.address = address
        self.subject = subject
        self.primer = primer
        self.target_bytes: int | None = None

    def resolve(self, complete: bytes) -> int | None:
        if self.target_bytes is not None:
            return self.target_bytes
        if len(complete) <= HPKE_ENCAPSULATED_KEY_BYTES:
            return None
        encapsulated_key = complete[:HPKE_ENCAPSULATED_KEY_BYTES]
        available = min(3, len(complete) - HPKE_ENCAPSULATED_KEY_BYTES)
        masked_header = complete[
            HPKE_ENCAPSULATED_KEY_BYTES : HPKE_ENCAPSULATED_KEY_BYTES + available
        ]
        clear_header = _xor(
            masked_header,
            _mask(self.address, encapsulated_key, self.subject, self.primer, available),
        )
        try:
            payload_length, header_bytes = decode_uvarint(clear_header, 0, max_bytes=3)
        except EOFError:
            return None
        except ValueError as error:
            raise OuterFrameError("stream has an invalid masked length") from error
        if payload_length > MAX_STEGO_PAYLOAD_BYTES:
            raise OuterFrameError("stream declaration exceeds protocol limit")
        self.target_bytes = HPKE_ENCAPSULATED_KEY_BYTES + header_bytes + payload_length
        return self.target_bytes


def unpack_stream(address: Address, stream: bytes, subject: str, primer: str) -> bytes:
    """Recover the HPKE blob after exact stream validation."""
    if len(stream) > MAX_STREAM_BYTES or len(stream) <= HPKE_ENCAPSULATED_KEY_BYTES:
        raise OuterFrameError("stream length is outside protocol bounds")
    resolver = StreamLengthResolver(address, subject, primer)
    target = resolver.resolve(stream[: HPKE_ENCAPSULATED_KEY_BYTES + 3])
    if target is None or target != len(stream):
        raise OuterFrameError("stream length does not match its declaration")
    encapsulated_key = stream[:HPKE_ENCAPSULATED_KEY_BYTES]
    masked_tail = stream[HPKE_ENCAPSULATED_KEY_BYTES:]
    clear_tail = _xor(
        masked_tail,
        _mask(address, encapsulated_key, subject, primer, len(masked_tail)),
    )
    try:
        payload_length, header_bytes = decode_uvarint(clear_tail, 0, max_bytes=3)
    except (EOFError, ValueError) as error:
        raise OuterFrameError("stream has an invalid clear length") from error
    payload = clear_tail[header_bytes:]
    if len(payload) != payload_length:
        raise OuterFrameError("stream payload length mismatch")
    ciphertext = parse_outer_payload(address, payload)
    return encapsulated_key + ciphertext
