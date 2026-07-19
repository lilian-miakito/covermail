from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.canonical import encode_base64url


@pytest.fixture
def private_key() -> x25519.X25519PrivateKey:
    return x25519.X25519PrivateKey.from_private_bytes(bytes(range(1, 33)))


@pytest.fixture
def address(private_key: x25519.X25519PrivateKey) -> dict[str, Any]:
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return {
        "format": "covermail-address",
        "version": 1,
        "recipient": {"label": "Alice", "hpke_public_key": encode_base64url(public)},
        "hpke": {
            "kem": "DHKEM_X25519_HKDF_SHA256",
            "kdf": "HKDF_SHA256",
            "aead": "AES_128_GCM",
            "mode": "BASE",
        },
        "model": {
            "backend": "mlx-lm",
            "model_id": "example/test-model",
            "revision": "0123456789abcdef0123456789abcdef01234567",
            "artifacts": [{"path": "config.json", "size": 2, "sha256": "0" * 64}],
            "runtime": {
                "profile": "test",
                "python_version": "3.12.5",
                "packages": {"cryptography": "49.0.0"},
                "logits_dtype": "float32",
                "trust_remote_code": False,
            },
        },
        "codec": {
            "id": "cm-arithmetic",
            "top_n": 4,
            "candidate_pool_multiplier": 2,
            "frequency_total": 32768,
            "logit_scale": 1024,
            "temperature_milli": 1000,
            "finish_tokens": 32,
            "visible_filter": "cm-visible-email",
            "prompt_template": "cm-email-continuation",
            "self_test": {
                "steps": 4,
                "path_indices": [0, 1, 3, 0],
                "expected_sha256": "1" * 64,
            },
        },
        "cover": {
            "language": "fr-FR",
            "relationship": "deux amis proches",
            "tone": "familier",
            "persona_sender": "une personne ordinaire",
            "persona_recipient": "un ami",
            "standing_context": "Des nouvelles du quotidien.",
            "max_visible_characters": 4000,
        },
    }


@pytest.fixture
def copied_address(address: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(address)


@pytest.fixture
def address_file(tmp_path: Path, address: dict[str, Any]) -> Path:
    path = tmp_path / "address.json"
    path.write_text(json.dumps(address), encoding="utf-8")
    return path
