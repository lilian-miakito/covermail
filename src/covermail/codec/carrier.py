"""High-level A/B/C/D carrier orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import Address
from covermail.codec.candidates import GreedyTokenModel, TokenModel
from covermail.codec.generative import (
    DEFAULT_FINISH_TOKENS,
    DEFAULT_PREFIX_TOKENS,
    MAX_FAKE_CARRIER_CHARACTERS,
    CarrierDecodeProgress,
    CarrierResult,
    CarrierTokenEvent,
    DecodedCarrier,
    decode_carrier_sections,
    encode_carrier_sections,
    generate_prefix_tokens,
)
from covermail.cover.transport import canonical_carrier
from covermail.protocol.packet import parse_header
from covermail.service import (
    EncryptedPacket,
    decrypt_message,
    encrypt_message,
)


@dataclass(frozen=True, slots=True)
class DecodedMessage:
    message_id: bytes
    secret: str
    carrier: DecodedCarrier


def encode_carrier(
    secret: str,
    prefix_model: TokenModel,
    payload_model: TokenModel,
    finish_model: GreedyTokenModel,
    address: Address,
    *,
    prefix_tokens: int = DEFAULT_PREFIX_TOKENS,
    finish_tokens: int = DEFAULT_FINISH_TOKENS,
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
    random_below: Callable[[int], int] | None = None,
    on_token: Callable[[CarrierTokenEvent], None] | None = None,
) -> CarrierResult:
    if random_below is None:
        prefix = generate_prefix_tokens(prefix_model, count=prefix_tokens, on_token=on_token)
    else:
        prefix = generate_prefix_tokens(
            prefix_model,
            count=prefix_tokens,
            random_below=random_below,
            on_token=on_token,
        )
    packet = encrypt_message(address, secret, prefix)
    return encode_carrier_sections(
        prefix,
        packet.header,
        packet.capsule,
        payload_model,
        finish_model,
        finish_tokens=finish_tokens,
        maximum_characters=maximum_characters,
        on_token=on_token,
    )


def decode_carrier(
    carrier: str,
    payload_model: TokenModel,
    address: Address,
    private_key: x25519.X25519PrivateKey,
    *,
    prefix_tokens: int = DEFAULT_PREFIX_TOKENS,
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
    on_token: Callable[[CarrierDecodeProgress], None] | None = None,
) -> DecodedMessage:
    def packet_layout(
        available: bytes, prefix: tuple[int, ...]
    ) -> tuple[int, int] | None:
        del prefix
        parsed = parse_header(available)
        if parsed is None:
            return None
        capsule_bytes, header_bytes = parsed
        return header_bytes, capsule_bytes

    decoded = decode_carrier_sections(
        canonical_carrier(carrier),
        payload_model,
        prefix_tokens=prefix_tokens,
        packet_layout_resolver=packet_layout,
        maximum_characters=maximum_characters,
        on_token=on_token,
    )
    message_id, secret = decrypt_message(
        address,
        private_key,
        EncryptedPacket(decoded.header, decoded.capsule),
        decoded.prefix_token_ids,
    )
    return DecodedMessage(message_id, secret, decoded)
