from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from covermail.address.canonical import canonical_json
from covermail.cli import main
from covermail.models.mlx_adapter import MODEL_ARTIFACT_PATHS

BRIEF = "Écris à un ami à propos du jardin."


def _fake_profile(model: object) -> SimpleNamespace:
    return SimpleNamespace(
        prefix_model=model,
        payload_model=model,
        finish_model=model,
        self_test=SimpleNamespace(
            selected_token_ids=(10, 11, 12, 13),
            sha256="a" * 64,
        ),
    )


def test_cli_identity_carrier_round_trip(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
    capsys: Any,
) -> None:
    from covermail.codec.fake_model import FakeLanguageModel

    template = tmp_path / "template.json"
    public = tmp_path / "alice.json"
    secret = tmp_path / "secret.txt"
    carrier = tmp_path / "carrier.txt"
    recovered = tmp_path / "recovered.txt"
    identities = tmp_path / "identities"
    template.write_bytes(canonical_json(address))
    secret.write_text("Message CLI — contexte lié", encoding="utf-8")
    answers = iter(["passphrase", "passphrase", "passphrase"])
    monkeypatch.setattr("covermail.cli.getpass.getpass", lambda prompt: next(answers))
    model = FakeLanguageModel()
    monkeypatch.setattr(
        "covermail.cli.load_profile",
        lambda address, model_root, writing_brief="": _fake_profile(model),
    )

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
                "carrier-encode",
                str(public),
                "--model-root",
                str(tmp_path),
                "--prompt",
                BRIEF,
                "--message",
                str(secret),
                "--output",
                str(carrier),
            ]
        )
        == 0
    )
    metrics = json.loads(capsys.readouterr().err)
    assert metrics["k_all"] == metrics["characters"] / metrics["packet_bytes"]
    assert metrics["metrics"]["prefix_tokens"] == 64

    assert (
        main(
            [
                "carrier-decode",
                identity_dir,
                "--model-root",
                str(tmp_path),
                "--carrier",
                str(carrier),
                "--output",
                str(recovered),
            ]
        )
        == 0
    )
    assert recovered.read_text(encoding="utf-8") == secret.read_text(encoding="utf-8")


def test_cli_rejects_oversized_secret_before_model_work(
    tmp_path: Path, address_file: Path, monkeypatch: Any, capsys: Any
) -> None:
    secret = tmp_path / "large.txt"
    secret.write_bytes(b"x" * 65536)
    monkeypatch.setattr(
        "covermail.cli.load_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("model loaded")),
    )
    try:
        main(
            [
                "carrier-encode",
                str(address_file),
                "--model-root",
                str(tmp_path),
                "--prompt",
                BRIEF,
                "--message",
                str(secret),
                "--output",
                str(tmp_path / "carrier.txt"),
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
    assert main(["model-prepare", "--source", str(source), "--destination", str(destination)]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert [entry["path"] for entry in manifest] == sorted(MODEL_ARTIFACT_PATHS)


def test_cli_generates_and_cross_verifies_qualification_bundle(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
    capsys: Any,
) -> None:
    from covermail.codec.fake_model import FakeLanguageModel

    address_path = tmp_path / "address.json"
    bundle_path = tmp_path / "qualification.json"
    verification_path = tmp_path / "verification.json"
    model = FakeLanguageModel()
    address_path.write_bytes(canonical_json(address))
    monkeypatch.setattr(
        "covermail.models.qualification.load_profile",
        lambda address, model_root, writing_brief="": _fake_profile(model),
    )
    monkeypatch.setattr(
        "covermail.models.qualification.quality_signals", lambda carrier: {"flags": []}
    )
    assert (
        main(
            [
                "model-qualify",
                str(address_path),
                "--model-root",
                str(tmp_path),
                "--output",
                str(bundle_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().err.splitlines()[-1])["action"] == "generated"
    assert (
        main(
            [
                "model-qualify",
                str(address_path),
                "--model-root",
                str(tmp_path),
                "--verify-bundle",
                str(bundle_path),
                "--output",
                str(verification_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().err.splitlines()[-1])["action"] == "verified"
    assert json.loads(verification_path.read_text())["all_packets_exact"]
