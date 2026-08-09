from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from fastapi.testclient import TestClient

from covermail.address.canonical import canonical_json
from covermail.codec.fake_model import FakeLanguageModel
from covermail.models.profile import LoadedProfile
from covermail.web.app import AppConfig, create_app

HEADERS: dict[str, str] = {}
BRIEF = "Write to a friend about the garden."


def _app(tmp_path: Path, address: dict[str, Any]) -> tuple[TestClient, Path]:
    template = tmp_path / "template.json"
    identities = tmp_path / "identities"
    template.write_bytes(canonical_json(address))
    model = FakeLanguageModel()

    def fake_loader(
        loaded_address: object,
        root: Path,
        writing_brief: str,
        adapter: object,
    ) -> LoadedProfile:
        del loaded_address, root, writing_brief, adapter
        return cast(
            LoadedProfile,
            SimpleNamespace(
                prefix_model=model,
                payload_model=model,
                finish_model=model,
                self_test=SimpleNamespace(sha256="a" * 64),
            ),
        )

    app = create_app(
        AppConfig(
            model_root=tmp_path,
            identities_dir=identities,
            template_path=template,
        ),
        profile_loader=fake_loader,
    )
    return TestClient(app, base_url="http://testserver"), identities


def _wait_job(client: TestClient, job_id: str) -> dict[str, Any]:
    for _ in range(200):
        response = client.get(f"/api/v1/jobs/{job_id}", headers=HEADERS)
        value = cast(dict[str, Any], response.json())
        if value["state"] in {"complete", "failed", "cancelled"}:
            return value
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_local_shell_accepts_hosts_and_rejects_large_body(
    tmp_path: Path,
    address: dict[str, Any],
) -> None:
    client, _ = _app(tmp_path, address)

    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health", headers={"host": "anything.local"}).status_code == 200
    assert client.get("/api/v1/identities").status_code == 200
    assert (
        client.get(
            "/api/v1/identities",
            headers={**HEADERS, "origin": "https://evil.example"},
        ).status_code
        == 200
    )
    oversized = "x" * ((1 << 20) + 1)
    assert (
        client.post(
            "/api/v1/addresses/inspect",
            content=oversized,
            headers={**HEADERS, "content-type": "application/json"},
        ).status_code
        == 413
    )
    response = client.get("/api/v1/identities", headers=HEADERS)
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "access-control-allow-origin" not in response.headers


def test_passphrase_is_absent_from_validation_response(
    tmp_path: Path,
    address: dict[str, Any],
) -> None:
    client, _ = _app(tmp_path, address)
    response = client.post(
        "/api/v1/identities",
        headers=HEADERS,
        json={
            "label": "",
            "passphrase": "do-not-leak-this-value",
            "passphrase_confirmation": "do-not-leak-this-value",
        },
    )
    assert response.status_code == 422
    assert "do-not-leak-this-value" not in response.text


def test_full_web_identity_encode_stream_and_decode_round_trip(
    tmp_path: Path,
    address: dict[str, Any],
) -> None:
    client, _ = _app(tmp_path, address)
    with client:
        created_response = client.post(
            "/api/v1/identities",
            headers=HEADERS,
            json={
                "label": "Alice locale",
                "passphrase": "phrase-secrete",
                "passphrase_confirmation": "phrase-secrete",
            },
        )
        assert created_response.status_code == 201, created_response.text
        created = cast(dict[str, Any], created_response.json())
        public_address = created["address"]

        estimate = client.post(
            "/api/v1/messages/estimate",
            headers=HEADERS,
            json={
                "address": public_address,
                "prompt": BRIEF,
                "secret": "Meet me at 6 p.m.",
            },
        )
        assert estimate.status_code == 200
        assert estimate.json()["packet_bytes"] > 53
        assert estimate.json()["hpke_overhead_bytes"] == 96
        assert estimate.json()["compressed_body_bytes"] > 0

        encode = client.post(
            "/api/v1/messages/encode",
            headers=HEADERS,
            json={
                "address": public_address,
                "prompt": BRIEF,
                "secret": "Meet me at 6 p.m.",
                "fingerprint_confirmed": True,
                "live_preview": True,
            },
        )
        assert encode.status_code == 202
        encode_job_id = encode.json()["job_id"]
        events = client.get(
            f"/api/v1/jobs/{encode_job_id}/events",
            headers=HEADERS,
        )
        assert events.status_code == 200
        assert "event: token" in events.text
        assert '"section":"A"' in events.text
        assert '"section":"B"' in events.text
        assert '"section":"C"' in events.text
        encoded = _wait_job(client, encode_job_id)
        assert encoded["state"] == "complete"
        carrier = encoded["result"]["carrier"]
        annotations = encoded["result"]["token_annotations"]
        assert "".join(annotation["text"] for annotation in annotations) == carrier
        assert [annotation["section"] for annotation in annotations[:64]] == ["A"] * 64
        assert sum(annotation["section"] == "D" for annotation in annotations) == encoded[
            "result"
        ]["metrics"]["finish_tokens"]
        assert {annotation["section"] for annotation in annotations} >= {"A", "B", "C", "D"}
        assert [annotation["token_index"] for annotation in annotations] == list(
            range(1, len(annotations) + 1)
        )
        assert carrier.endswith("amicalement.")

        decode = client.post(
            "/api/v1/messages/decode",
            headers=HEADERS,
            json={
                "identity_id": created["address_id"],
                "passphrase": "phrase-secrete",
                "carrier": carrier,
            },
        )
        assert decode.status_code == 202
        decoded = _wait_job(client, decode.json()["job_id"])
        assert decoded["state"] == "complete"
        assert decoded["result"]["secret"] == "Meet me at 6 p.m."


def test_address_inspection_and_identity_listing(
    tmp_path: Path,
    address: dict[str, Any],
) -> None:
    client, _ = _app(tmp_path, address)
    with client:
        inspected = client.post(
            "/api/v1/addresses/inspect",
            headers={**HEADERS, "content-type": "application/json"},
            content=json.dumps({"address": address}),
        )
        assert inspected.status_code == 200
        assert inspected.json()["label"] == "Alice"
        assert client.get("/api/v1/identities", headers=HEADERS).json() == {"identities": []}
