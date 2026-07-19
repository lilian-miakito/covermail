from __future__ import annotations

import copy
from typing import Any

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import validate_address
from covermail.codec.fake_model import FakeLanguageModel
from covermail.codec.v2 import decode_v2_carrier, encode_v2_carrier
from covermail.service_v2 import decrypt_message_v2, encrypt_message_v2


def test_v2_fake_model_primer_stream_and_hpke_round_trip(
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    mutated = copy.deepcopy(address)
    mutated["codec"]["id"] = "cm-arithmetic-v2"
    mutated["codec"]["length_bias_milli"] = 0
    mutated["codec"]["prompt_template"] = "cm-email-continue-primer-v2"
    validated = validate_address(mutated)
    subject = "Sujet v2"
    primer = "abc."
    model = FakeLanguageModel()
    primer_ids = tuple(model.tokenize(primer))
    stream = encrypt_message_v2(validated, "Message à travers v2", subject, primer)
    carrier = encode_v2_carrier(
        stream,
        model,
        validated,
        subject,
        primer,
        primer_ids,
    )
    assert carrier.text.startswith(primer)
    assert carrier.metrics.primer_tokens == len(primer_ids)
    recovered = decode_v2_carrier(
        carrier.text,
        model,
        validated,
        subject,
        primer,
        primer_ids,
    )
    assert recovered == stream
    assert decrypt_message_v2(validated, private_key, recovered, subject, primer)[1] == (
        "Message à travers v2"
    )
