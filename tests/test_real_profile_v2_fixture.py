from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.canonical import read_address_file
from covermail.address.schema import validate_address
from covermail.cover.primer import extract_primer
from covermail.service_v2 import decrypt_message_v2


def test_real_v2_profile_fixture_is_valid_and_decrypts() -> None:
    directory = Path(__file__).parent / "fixtures/mlx_llama32_3b_4bit_v2"
    address = validate_address(read_address_file(directory / "address.json"))
    fixture = json.loads((directory / "fixture.json").read_text(encoding="utf-8"))
    carrier = (directory / "carrier.txt").read_text(encoding="utf-8").removesuffix("\n")
    stream = base64.b64decode(fixture["stream_base64"], validate=True)
    private_key = x25519.X25519PrivateKey.from_private_bytes(bytes(range(1, 33)))

    assert address["codec"]["id"] == "cm-arithmetic-v2"
    assert address["codec"]["length_bias_milli"] == 0
    assert extract_primer(carrier) == fixture["primer"]
    assert len(stream) == fixture["stream_bytes"]
    assert len(carrier) == fixture["metrics"]["characters_all"]
    assert len(carrier) / len(stream) == fixture["ratios"]["k_all_characters_per_stream_byte"]
    _, plaintext = decrypt_message_v2(
        address,
        private_key,
        stream,
        fixture["subject"],
        fixture["primer"],
    )
    assert plaintext == fixture["plaintext"]
