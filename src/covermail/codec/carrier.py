"""Primer-aware carrier orchestration for Covermail."""

from __future__ import annotations

from covermail.address.schema import Address
from covermail.codec.candidates import TokenModel
from covermail.codec.generative import (
    DEFAULT_FINISH_TOKENS,
    MAX_FAKE_CARRIER_CHARACTERS,
    CarrierResult,
    decode_carrier_stream,
    encode_carrier_stream,
)
from covermail.cover.transport import canonical_carrier
from covermail.protocol.stego_stream import StreamLengthResolver, unpack_stream


def encode_carrier(
    stream: bytes,
    model: TokenModel,
    address: Address,
    subject: str,
    primer: str,
    primer_ids: tuple[int, ...],
    *,
    finish_tokens: int = DEFAULT_FINISH_TOKENS,
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
) -> CarrierResult:
    unpack_stream(address, stream, subject, primer)
    return encode_carrier_stream(
        stream,
        model,
        initial_token_ids=primer_ids,
        finish_tokens=finish_tokens,
        maximum_characters=maximum_characters,
    )


def decode_carrier(
    carrier: str,
    model: TokenModel,
    address: Address,
    subject: str,
    primer: str,
    primer_ids: tuple[int, ...],
    *,
    finish_tokens: int = DEFAULT_FINISH_TOKENS,
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
) -> bytes:
    resolver = StreamLengthResolver(address, subject, primer)

    def validate(stream: bytes) -> None:
        unpack_stream(address, stream, subject, primer)

    return decode_carrier_stream(
        canonical_carrier(carrier),
        model,
        length_resolver=resolver.resolve,
        final_validator=validate,
        initial_token_ids=primer_ids,
        finish_tokens=finish_tokens,
        maximum_characters=maximum_characters,
    )
