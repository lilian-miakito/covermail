from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from covermail.address.canonical import canonical_json
from covermail.cli import main
from covermail.models.mlx_adapter import MODEL_ARTIFACT_PATHS


def test_cli_independent_binary_round_trip(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
    capsys: Any,
) -> None:
    template = tmp_path / "template.json"
    public = tmp_path / "alice.json"
    secret = tmp_path / "secret.txt"
    frame = tmp_path / "message.cm"
    recovered = tmp_path / "recovered.txt"
    identities = tmp_path / "identities"
    template.write_bytes(canonical_json(address))
    secret.write_text("Message CLI indépendant — été 2026", encoding="utf-8")

    answers = iter(["passphrase", "passphrase", "passphrase"])
    monkeypatch.setattr("covermail.cli.getpass.getpass", lambda prompt: next(answers))

    assert main(
        [
            "identity-create",
            str(template),
            "--identities-dir",
            str(identities),
            "--public-address",
            str(public),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    identity_dir = created["identity_dir"]

    assert main(
        ["encrypt", str(public), "--message", str(secret), "--output", str(frame)]
    ) == 0
    capsys.readouterr()
    assert main(
        ["decrypt", identity_dir, "--frame", str(frame), "--output", str(recovered)]
    ) == 0
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
                "--message",
                str(secret),
                "--output",
                str(tmp_path / "message.cm"),
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    assert "exceeds protocol limit" in capsys.readouterr().err


def test_cli_fake_carrier_round_trip(tmp_path: Path, capsys: Any) -> None:
    frame = tmp_path / "message.cm"
    carrier = tmp_path / "carrier.txt"
    recovered = tmp_path / "recovered.cm"
    from covermail.protocol.outer_frame import pack_stego_frame

    frame.write_bytes(pack_stego_frame(b"CLI Stage 2"))
    assert main(["fake-encode", "--frame", str(frame), "--output", str(carrier)]) == 0
    encode_status = capsys.readouterr().err
    assert '"tokens"' in encode_status
    assert carrier.read_text(encoding="utf-8").endswith(".")

    assert main(
        ["fake-decode", "--carrier", str(carrier), "--output", str(recovered)]
    ) == 0
    assert recovered.read_bytes() == frame.read_bytes()


def test_cli_fake_decode_allows_exactly_one_terminal_line_ending(
    tmp_path: Path, capsys: Any
) -> None:
    from covermail.codec.fake_model import FakeLanguageModel
    from covermail.codec.generative import encode_carrier
    from covermail.protocol.outer_frame import pack_stego_frame

    frame = pack_stego_frame(b"terminal line ending")
    carrier = encode_carrier(frame, FakeLanguageModel()).text
    carrier_path = tmp_path / "carrier.txt"
    output = tmp_path / "decoded.cm"
    carrier_path.write_text(carrier + "\r\n", encoding="utf-8", newline="")
    assert main(
        ["fake-decode", "--carrier", str(carrier_path), "--output", str(output)]
    ) == 0
    capsys.readouterr()
    assert output.read_bytes() == frame


def test_cli_model_prepare_materializes_regular_tree(tmp_path: Path, capsys: Any) -> None:
    source = tmp_path / "snapshot"
    destination = tmp_path / "qualified"
    source.mkdir()
    for index, relative_path in enumerate(MODEL_ARTIFACT_PATHS):
        (source / relative_path).write_bytes(f"artifact-{index}".encode())

    assert main(
        [
            "model-prepare",
            "--source",
            str(source),
            "--destination",
            str(destination),
        ]
    ) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert [entry["path"] for entry in manifest] == sorted(MODEL_ARTIFACT_PATHS)
    assert all((destination / path).is_file() for path in MODEL_ARTIFACT_PATHS)


def test_cli_v2_context_bound_binary_round_trip(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
    capsys: Any,
) -> None:
    template_address = copy.deepcopy(address)
    template_address["codec"]["id"] = "cm-arithmetic-v2"
    template_address["codec"]["length_bias_milli"] = 0
    template_address["codec"]["prompt_template"] = "cm-email-continue-primer-v2"
    template = tmp_path / "template-v2.json"
    public = tmp_path / "alice-v2.json"
    secret = tmp_path / "secret-v2.txt"
    stream = tmp_path / "message.cm2"
    recovered = tmp_path / "recovered-v2.txt"
    identities = tmp_path / "identities-v2"
    subject = "Des nouvelles du jardin"
    primer = "Je voulais te raconter calmement ce qui s'est passé."
    template.write_bytes(canonical_json(template_address))
    secret.write_text("Message CLI v2 — contexte lié", encoding="utf-8")
    answers = iter(["passphrase", "passphrase", "passphrase"])
    monkeypatch.setattr("covermail.cli.getpass.getpass", lambda prompt: next(answers))

    assert main(
        [
            "identity-create",
            str(template),
            "--identities-dir",
            str(identities),
            "--public-address",
            str(public),
        ]
    ) == 0
    identity_dir = json.loads(capsys.readouterr().out)["identity_dir"]
    assert main(
        [
            "encrypt-v2",
            str(public),
            "--subject",
            subject,
            "--primer",
            primer,
            "--message",
            str(secret),
            "--output",
            str(stream),
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "decrypt-v2",
            identity_dir,
            "--subject",
            subject,
            "--primer",
            primer,
            "--stream",
            str(stream),
            "--output",
            str(recovered),
        ]
    ) == 0
    assert recovered.read_text(encoding="utf-8") == secret.read_text(encoding="utf-8")


def test_cli_v2_fake_adapter_carrier_round_trip_and_k_all(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
    capsys: Any,
) -> None:
    from covermail.codec.fake_model import FakeLanguageModel
    from covermail.service_v2 import encrypt_message_v2

    v2_address = copy.deepcopy(address)
    v2_address["codec"]["id"] = "cm-arithmetic-v2"
    v2_address["codec"]["length_bias_milli"] = 0
    v2_address["codec"]["prompt_template"] = "cm-email-continue-primer-v2"
    address_path = tmp_path / "address-v2.json"
    stream_path = tmp_path / "message.cm2"
    carrier_path = tmp_path / "carrier.txt"
    recovered_path = tmp_path / "decoded.cm2"
    primer_path = tmp_path / "primer.txt"
    subject = "Sujet v2"
    primer = "abc."
    model = FakeLanguageModel()
    primer_ids = tuple(model.tokenize(primer))
    address_path.write_bytes(canonical_json(v2_address))
    stream = encrypt_message_v2(v2_address, "carrier CLI v2", subject, primer)
    stream_path.write_bytes(stream)
    monkeypatch.setattr(
        "covermail.cli.load_profile",
        lambda address, model_root, visible_subject, visible_primer=None: SimpleNamespace(
            model=model,
            primer_ids=primer_ids,
        ),
    )

    assert main(
        [
            "carrier-encode",
            str(address_path),
            "--model-root",
            str(tmp_path),
            "--subject",
            subject,
            "--primer",
            primer,
            "--frame",
            str(stream_path),
            "--output",
            str(carrier_path),
        ]
    ) == 0
    metrics = json.loads(capsys.readouterr().err)
    assert metrics["k_all"] == metrics["characters"] / metrics["stream_bytes"]
    assert metrics["metrics"]["primer_tokens"] == len(primer_ids)

    assert main(
        [
            "carrier-decode",
            str(address_path),
            "--model-root",
            str(tmp_path),
            "--subject",
            subject,
            "--carrier",
            str(carrier_path),
            "--output",
            str(recovered_path),
            "--primer-output",
            str(primer_path),
        ]
    ) == 0
    assert recovered_path.read_bytes() == stream
    assert primer_path.read_text(encoding="utf-8") == primer
