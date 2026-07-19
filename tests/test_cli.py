from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from covermail.address.canonical import canonical_json
from covermail.cli import main


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
