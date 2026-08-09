"""Offline Covermail protocol and qualified model CLI."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

from covermail.address.canonical import canonical_json, read_address_file
from covermail.address.fingerprint import human_fingerprint, machine_address_id
from covermail.address.schema import Address, validate_address
from covermail.codec.carrier import decode_carrier, encode_carrier
from covermail.cover.transport import canonical_carrier
from covermail.crypto.identity import generate_identity
from covermail.crypto.private_store import save_identity, unlock_identity
from covermail.errors import CovermailError
from covermail.models.manifest import build_artifact_manifest, materialize_artifact_tree
from covermail.models.mlx_adapter import MODEL_ARTIFACT_PATHS
from covermail.models.profile import load_profile
from covermail.models.qualification import (
    generate_qualification_bundle,
    read_qualification_bundle,
    verify_qualification_bundle,
)
from covermail.protocol.inner_frame import MAX_SECRET_UTF8_BYTES


def _address(path: Path) -> Address:
    return validate_address(read_address_file(path))


def _read_limited(path: str, maximum: int) -> bytes:
    if path == "-":
        raw = sys.stdin.buffer.read(maximum + 1)
    else:
        with Path(path).open("rb") as stream:
            raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise CovermailError("input exceeds protocol limit")
    return raw


def _read_text(path: str) -> str:
    raw = _read_limited(path, MAX_SECRET_UTF8_BYTES)
    return raw.decode("utf-8", errors="strict")


def _write_bytes(path: str, data: bytes) -> None:
    if path == "-":
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    else:
        Path(path).write_bytes(data)


def _write_text(path: str, text: str) -> None:
    data = text.encode("utf-8", errors="strict")
    if path == "-":
        _write_bytes(path, data)
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        if os.name == "posix":
            os.fchmod(stream.fileno(), 0o600)
        stream.write(data)


def _passphrase(*, confirm: bool) -> str:
    first = getpass.getpass("Private-key passphrase: ")
    if confirm and first != getpass.getpass("Confirm passphrase: "):
        raise CovermailError("passphrases do not match")
    return first


def _create_identity(args: argparse.Namespace) -> int:
    template = read_address_file(args.template)
    address, private_key = generate_identity(template)
    identity_dir = save_identity(
        args.identities_dir, address, private_key, _passphrase(confirm=True)
    )
    if args.public_address is not None:
        args.public_address.write_bytes(canonical_json(address) + b"\n")
    result = {
        "address_id": machine_address_id(address),
        "fingerprint": human_fingerprint(address),
        "identity_dir": str(identity_dir),
        "public_address": str(args.public_address) if args.public_address is not None else None,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _inspect_address(args: argparse.Namespace) -> int:
    address = _address(args.address)
    result = {
        "address_id": machine_address_id(address),
        "fingerprint": human_fingerprint(address),
        "label": address["recipient"]["label"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _carrier_text(raw: bytes) -> str:
    """Decode UTF-8 and remove at most one text-area/file terminal line ending."""
    text = raw.decode("utf-8", errors="strict")
    if text.endswith("\r\n"):
        return text[:-2]
    if text.endswith(("\r", "\n")):
        return text[:-1]
    return canonical_carrier(text)


def _model_prepare(args: argparse.Namespace) -> int:
    materialize_artifact_tree(args.source, args.destination, MODEL_ARTIFACT_PATHS)
    manifest = build_artifact_manifest(args.destination, MODEL_ARTIFACT_PATHS)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _model_self_test(args: argparse.Namespace) -> int:
    address = _address(args.address)
    loaded = load_profile(address, args.model_root)
    print(
        json.dumps(
            {
                "selected_token_ids": loaded.self_test.selected_token_ids,
                "sha256": loaded.self_test.sha256,
            },
            sort_keys=True,
        )
    )
    return 0


def _model_qualify(args: argparse.Namespace) -> int:
    address = _address(args.address)

    def progress(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    if args.verify_bundle is None:
        report = generate_qualification_bundle(address, args.model_root, progress=progress)
        action = "generated"
    else:
        bundle = read_qualification_bundle(args.verify_bundle)
        report = verify_qualification_bundle(
            address,
            args.model_root,
            bundle,
            progress=progress,
        )
        action = "verified"
    _write_text(
        args.output,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    cases = report["cases"]
    if not isinstance(cases, list):
        raise CovermailError("qualification report has invalid cases")
    print(
        json.dumps(
            {
                "action": action,
                "cases": len(cases),
                "output": args.output,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return 0


def _carrier_encode(args: argparse.Namespace) -> int:
    address = _address(args.address)
    codec = address["codec"]
    cover = address["cover"]
    secret = _read_text(args.message)
    loaded = load_profile(address, args.model_root, args.prompt)
    started = time.perf_counter()
    result = encode_carrier(
        secret,
        loaded.prefix_model,
        loaded.payload_model,
        loaded.finish_model,
        address,
        prefix_tokens=codec["prefix_tokens"],
        finish_tokens=args.finish_tokens,
        maximum_characters=cover["max_visible_characters"],
    )
    elapsed = time.perf_counter() - started
    _write_bytes(args.output, result.text.encode("utf-8"))
    if args.output != "-":
        metadata = {
            "characters": len(result.text),
            "elapsed_seconds": elapsed,
            "generated_tokens_per_second": len(result.token_ids) / elapsed,
            "k_all": len(result.text) / (len(result.metadata) + len(result.body)),
            "metrics": asdict(result.metrics),
            "packet_bytes": len(result.metadata) + len(result.body),
            "tokens": len(result.token_ids),
            "utf8_bytes": len(result.text.encode("utf-8")),
        }
        print(json.dumps(metadata, sort_keys=True), file=sys.stderr)
    return 0


def _carrier_decode(args: argparse.Namespace) -> int:
    address, private_key = unlock_identity(args.identity_dir, _passphrase(confirm=False))
    codec = address["codec"]
    cover = address["cover"]
    raw = _read_limited(args.carrier, cover["max_visible_characters"] * 4)
    carrier = _carrier_text(raw)
    loaded = load_profile(address, args.model_root)
    started = time.perf_counter()
    decoded = decode_carrier(
        carrier,
        loaded.payload_model,
        address,
        private_key,
        prefix_tokens=codec["prefix_tokens"],
        maximum_characters=cover["max_visible_characters"],
    )
    elapsed = time.perf_counter() - started
    _write_text(args.output, decoded.secret)
    if args.output != "-":
        print(
            json.dumps(
                {
                    "elapsed_seconds": elapsed,
                    "plaintext_utf8_bytes": len(decoded.secret.encode("utf-8")),
                    "consumed_tokens": decoded.carrier.consumed_tokens,
                    "tokens_per_second": decoded.carrier.consumed_tokens / elapsed,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
    return 0


def _local_app(args: argparse.Namespace) -> int:
    from covermail.web import AppConfig, run_local_app

    try:
        run_local_app(
            AppConfig(
                model_root=args.model_root,
                identities_dir=args.identities_dir,
                host=args.host,
                port=args.port,
                template_path=args.address_template,
            )
        )
    except ValueError as error:
        raise CovermailError(str(error)) from error
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="covermail",
        description="Covermail protocol and qualified offline carrier tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("identity-create", help="create an encrypted recipient identity")
    create.add_argument("template", type=Path, help="complete address template JSON")
    create.add_argument("--identities-dir", type=Path, required=True)
    create.add_argument("--public-address", type=Path)
    create.set_defaults(handler=_create_identity)

    inspect = subparsers.add_parser("address-inspect", help="validate and fingerprint an address")
    inspect.add_argument("address", type=Path)
    inspect.set_defaults(handler=_inspect_address)

    prepare = subparsers.add_parser(
        "model-prepare",
        help="materialize the qualified model snapshot and print its manifest",
    )
    prepare.add_argument("--source", type=Path, required=True, help="trusted snapshot directory")
    prepare.add_argument(
        "--destination", type=Path, required=True, help="new qualified artifact directory"
    )
    prepare.set_defaults(handler=_model_prepare)

    self_test = subparsers.add_parser(
        "model-self-test", help="verify artifacts, runtime, and address model self-test"
    )
    self_test.add_argument("address", type=Path)
    self_test.add_argument("--model-root", type=Path, required=True)
    self_test.set_defaults(handler=_model_self_test)

    qualify = subparsers.add_parser(
        "model-qualify",
        help="generate or cross-verify the fixed real-model qualification corpus",
    )
    qualify.add_argument("address", type=Path)
    qualify.add_argument("--model-root", type=Path, required=True)
    qualify.add_argument(
        "--verify-bundle",
        type=Path,
        help="decode and verify a bundle generated by another installation",
    )
    qualify.add_argument("--output", required=True, help="qualification JSON output, or -")
    qualify.set_defaults(handler=_model_qualify)

    carrier_encode = subparsers.add_parser(
        "carrier-encode", help="encrypt text and generate an A/B/C/D carrier"
    )
    carrier_encode.add_argument("address", type=Path)
    carrier_encode.add_argument("--model-root", type=Path, required=True)
    carrier_encode.add_argument("--prompt", required=True, help="free writing brief for A")
    carrier_encode.add_argument("--message", required=True, help="UTF-8 secret file, or -")
    carrier_encode.add_argument("--finish-tokens", type=int, default=128)
    carrier_encode.add_argument("--output", required=True, help="UTF-8 carrier file, or -")
    carrier_encode.set_defaults(handler=_carrier_encode)

    carrier_decode = subparsers.add_parser(
        "carrier-decode", help="recover plaintext from an A/B/C/D carrier"
    )
    carrier_decode.add_argument("identity_dir", type=Path)
    carrier_decode.add_argument("--model-root", type=Path, required=True)
    carrier_decode.add_argument("--carrier", required=True, help="UTF-8 carrier file, or -")
    carrier_decode.add_argument("--output", required=True, help="UTF-8 output file, or -")
    carrier_decode.set_defaults(handler=_carrier_decode)

    app = subparsers.add_parser("app", help="run the loopback-only Covermail web application")
    app.add_argument("--model-root", type=Path, required=True)
    app.add_argument(
        "--identities-dir",
        type=Path,
        default=Path(".covermail/identities"),
        help="encrypted local identity directory",
    )
    app.add_argument("--address-template", type=Path, help="advanced profile override")
    app.add_argument("--host", default="127.0.0.1", help="loopback IP literal only")
    app.add_argument("--port", type=int, default=8765)
    app.set_defaults(handler=_local_app)
    return parser


def _fail(message: str) -> NoReturn:
    print(f"covermail: {message}", file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        handler = args.handler
        if not callable(handler):
            return 2
        return int(handler(args))
    except (CovermailError, OSError, UnicodeError) as error:
        _fail(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
