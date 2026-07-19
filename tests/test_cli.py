from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from covermail.address.canonical import canonical_json
from covermail.cli import main
from covermail.models.mlx_adapter import MODEL_ARTIFACT_PATHS
from covermail.service import encrypt_message

SUBJECT = "Des nouvelles du jardin"
PRIMER = "abc."


def test_cli_context_bound_binary_round_trip(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
    capsys: Any,
) -> None:
    template = tmp_path / "template.json"
    public = tmp_path / "alice.json"
    secret = tmp_path / "secret.txt"
    stream = tmp_path / "message.cm"
    recovered = tmp_path / "recovered.txt"
    identities = tmp_path / "identities"
    template.write_bytes(canonical_json(address))
    secret.write_text("Message CLI — contexte lié", encoding="utf-8")
    answers = iter(["passphrase", "passphrase", "passphrase"])
    monkeypatch.setattr("covermail.cli.getpass.getpass", lambda prompt: next(answers))

    assert (
        main(
            [
                "identity-create",
                str(template),
                "--identities-dir",
                str(identities),
                "--public-address",
                str(public),
            ]
        )
        == 0
    )
    identity_dir = json.loads(capsys.readouterr().out)["identity_dir"]
    assert (
        main(
            [
                "encrypt",
                str(public),
                "--subject",
                SUBJECT,
                "--primer",
                PRIMER,
                "--message",
                str(secret),
                "--output",
                str(stream),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "decrypt",
                identity_dir,
                "--subject",
                SUBJECT,
                "--primer",
                PRIMER,
                "--stream",
                str(stream),
                "--output",
                str(recovered),
            ]
        )
        == 0
    )
    assert recovered.read_text(encoding="utf-8") == secret.read_text(encoding="utf-8")
    if os.name == "posix":
        assert recovered.stat().st_mode & 0o777 == 0o600


def test_cli_rejects_oversized_secret_before_protocol_work(
    tmp_path: Path,
    address_file: Path,
    capsys: Any,
) -> None:
    secret = tmp_path / "large.txt"
    secret.write_bytes(b"x" * 65536)
    try:
        main(
            [
                "encrypt",
                str(address_file),
                "--subject",
                SUBJECT,
                "--primer",
                PRIMER,
                "--message",
                str(secret),
                "--output",
                str(tmp_path / "message.cm"),
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    assert "exceeds protocol limit" in capsys.readouterr().err


def test_cli_model_prepare_materializes_regular_tree(tmp_path: Path, capsys: Any) -> None:
    source = tmp_path / "snapshot"
    destination = tmp_path / "qualified"
    source.mkdir()
    for index, relative_path in enumerate(MODEL_ARTIFACT_PATHS):
        (source / relative_path).write_bytes(f"artifact-{index}".encode())

    assert (
        main(
            [
                "model-prepare",
                "--source",
                str(source),
                "--destination",
                str(destination),
            ]
        )
        == 0
    )
    manifest = json.loads(capsys.readouterr().out)
    assert [entry["path"] for entry in manifest] == sorted(MODEL_ARTIFACT_PATHS)
    assert all((destination / path).is_file() for path in MODEL_ARTIFACT_PATHS)


def test_cli_fake_adapter_carrier_round_trip_and_k_all(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
    capsys: Any,
) -> None:
    from covermail.codec.fake_model import FakeLanguageModel

    address_path = tmp_path / "address.json"
    stream_path = tmp_path / "message.cm"
    carrier_path = tmp_path / "carrier.txt"
    recovered_path = tmp_path / "decoded.cm"
    primer_path = tmp_path / "primer.txt"
    model = FakeLanguageModel()
    primer_ids = tuple(model.tokenize(PRIMER))
    address_path.write_bytes(canonical_json(address))
    stream = encrypt_message(address, "carrier CLI", SUBJECT, PRIMER)
    stream_path.write_bytes(stream)
    monkeypatch.setattr(
        "covermail.cli.load_profile",
        lambda address, model_root, subject, primer: SimpleNamespace(
            model=model,
            primer_ids=primer_ids,
        ),
    )

    assert (
        main(
            [
                "carrier-encode",
                str(address_path),
                "--model-root",
                str(tmp_path),
                "--subject",
                SUBJECT,
                "--primer",
                PRIMER,
                "--stream",
                str(stream_path),
                "--output",
                str(carrier_path),
            ]
        )
        == 0
    )
    metrics = json.loads(capsys.readouterr().err)
    assert metrics["k_all"] == metrics["characters"] / metrics["stream_bytes"]
    assert metrics["metrics"]["primer_tokens"] == len(primer_ids)

    assert (
        main(
            [
                "carrier-decode",
                str(address_path),
                "--model-root",
                str(tmp_path),
                "--subject",
                SUBJECT,
                "--carrier",
                str(carrier_path),
                "--output",
                str(recovered_path),
                "--primer-output",
                str(primer_path),
            ]
        )
        == 0
    )
    assert recovered_path.read_bytes() == stream
    assert primer_path.read_text(encoding="utf-8") == PRIMER
