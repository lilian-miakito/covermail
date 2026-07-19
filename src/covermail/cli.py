"""Offline Covermail protocol, fake codec, and qualified Stage 3 model CLI."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

from covermail.address.canonical import canonical_json, read_address_file
from covermail.address.fingerprint import human_fingerprint, machine_address_id
from covermail.address.schema import Address, validate_address
from covermail.codec.fake_model import FakeLanguageModel
from covermail.codec.generative import decode_carrier, encode_carrier
from covermail.crypto.identity import generate_identity
from covermail.crypto.private_store import save_identity, unlock_identity
from covermail.errors import CovermailError
from covermail.models.manifest import build_artifact_manifest, materialize_artifact_tree
from covermail.models.mlx_adapter import MODEL_ARTIFACT_PATHS
from covermail.models.profile import load_profile
from covermail.protocol.inner_frame import MAX_SECRET_UTF8_BYTES
from covermail.protocol.outer_frame import MAX_STEGO_PAYLOAD_BYTES
from covermail.service import decrypt_message, encrypt_message


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


def _read_bytes(path: str) -> bytes:
    return _read_limited(path, MAX_STEGO_PAYLOAD_BYTES + 3)


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


def _encrypt(args: argparse.Namespace) -> int:
    address = _address(args.address)
    frame = encrypt_message(address, _read_text(args.message))
    _write_bytes(args.output, frame)
    if args.output != "-":
        print(f"wrote {len(frame)} framed bytes", file=sys.stderr)
    return 0


def _decrypt(args: argparse.Namespace) -> int:
    address, private_key = unlock_identity(args.identity_dir, _passphrase(confirm=False))
    _, secret = decrypt_message(address, private_key, _read_bytes(args.frame))
    _write_text(args.output, secret)
    if args.output != "-":
        print(f"wrote {len(secret.encode('utf-8'))} plaintext bytes", file=sys.stderr)
    return 0


def _fake_encode(args: argparse.Namespace) -> int:
    model = FakeLanguageModel()
    result = encode_carrier(_read_bytes(args.frame), model)
    _write_bytes(args.output, result.text.encode("utf-8"))
    if args.output != "-":
        metadata = {"metrics": asdict(result.metrics), "tokens": len(result.token_ids)}
        print(json.dumps(metadata, sort_keys=True), file=sys.stderr)
    return 0


def _fake_decode(args: argparse.Namespace) -> int:
    raw = _read_limited(args.carrier, 800000)
    carrier = _carrier_text(raw)
    frame = decode_carrier(carrier, FakeLanguageModel())
    _write_bytes(args.output, frame)
    if args.output != "-":
        print(f"recovered {len(frame)} framed bytes", file=sys.stderr)
    return 0


def _carrier_text(raw: bytes) -> str:
    """Decode UTF-8 and remove at most one text-area/file terminal line ending."""
    text = raw.decode("utf-8", errors="strict")
    if text.endswith("\r\n"):
        return text[:-2]
    if text.endswith(("\r", "\n")):
        return text[:-1]
    return text


def _model_prepare(args: argparse.Namespace) -> int:
    materialize_artifact_tree(args.source, args.destination, MODEL_ARTIFACT_PATHS)
    manifest = build_artifact_manifest(args.destination, MODEL_ARTIFACT_PATHS)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _model_self_test(args: argparse.Namespace) -> int:
    address = _address(args.address)
    loaded = load_profile(address, args.model_root, args.subject)
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


def _carrier_encode(args: argparse.Namespace) -> int:
    address = _address(args.address)
    loaded = load_profile(address, args.model_root, args.subject)
    codec = address["codec"]
    cover = address["cover"]
    result = encode_carrier(
        _read_bytes(args.frame),
        loaded.model,
        finish_tokens=codec["finish_tokens"],
        maximum_characters=cover["max_visible_characters"],
    )
    _write_bytes(args.output, result.text.encode("utf-8"))
    if args.output != "-":
        metadata = {"metrics": asdict(result.metrics), "tokens": len(result.token_ids)}
        print(json.dumps(metadata, sort_keys=True), file=sys.stderr)
    return 0


def _carrier_decode(args: argparse.Namespace) -> int:
    address = _address(args.address)
    loaded = load_profile(address, args.model_root, args.subject)
    codec = address["codec"]
    cover = address["cover"]
    raw = _read_limited(args.carrier, cover["max_visible_characters"] * 4)
    frame = decode_carrier(
        _carrier_text(raw),
        loaded.model,
        finish_tokens=codec["finish_tokens"],
        maximum_characters=cover["max_visible_characters"],
    )
    _write_bytes(args.output, frame)
    if args.output != "-":
        print(f"recovered {len(frame)} framed bytes", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="covermail",
        description="Covermail v1 protocol and qualified offline carrier tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("identity-create", help="create an encrypted recipient identity")
    create.add_argument("template", type=Path, help="complete v1 address template JSON")
    create.add_argument("--identities-dir", type=Path, required=True)
    create.add_argument("--public-address", type=Path)
    create.set_defaults(handler=_create_identity)

    inspect = subparsers.add_parser("address-inspect", help="validate and fingerprint an address")
    inspect.add_argument("address", type=Path)
    inspect.set_defaults(handler=_inspect_address)

    encrypt = subparsers.add_parser("encrypt", help="encrypt UTF-8 text to a binary stego frame")
    encrypt.add_argument("address", type=Path)
    encrypt.add_argument("--message", required=True, help="UTF-8 file, or - for standard input")
    encrypt.add_argument(
        "--output", required=True, help="binary output file, or - for standard output"
    )
    encrypt.set_defaults(handler=_encrypt)

    decrypt = subparsers.add_parser("decrypt", help="decrypt a binary stego frame")
    decrypt.add_argument("identity_dir", type=Path)
    decrypt.add_argument(
        "--frame", required=True, help="binary input file, or - for standard input"
    )
    decrypt.add_argument(
        "--output", required=True, help="UTF-8 output file, or - for standard output"
    )
    decrypt.set_defaults(handler=_decrypt)

    fake_encode = subparsers.add_parser(
        "fake-encode", help="map a binary stego frame to a deterministic fake carrier"
    )
    fake_encode.add_argument("--frame", required=True, help="binary input file, or -")
    fake_encode.add_argument("--output", required=True, help="UTF-8 carrier output file, or -")
    fake_encode.set_defaults(handler=_fake_encode)

    fake_decode = subparsers.add_parser(
        "fake-decode", help="recover a binary stego frame from a fake carrier"
    )
    fake_decode.add_argument("--carrier", required=True, help="UTF-8 input file, or -")
    fake_decode.add_argument("--output", required=True, help="binary output file, or -")
    fake_decode.set_defaults(handler=_fake_decode)

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
    self_test.add_argument(
        "--subject", default="Covermail model readiness check", help="ordinary prompt smoke test"
    )
    self_test.set_defaults(handler=_model_self_test)

    carrier_encode = subparsers.add_parser(
        "carrier-encode", help="map a framed message to a qualified real-model carrier"
    )
    carrier_encode.add_argument("address", type=Path)
    carrier_encode.add_argument("--model-root", type=Path, required=True)
    carrier_encode.add_argument("--subject", required=True)
    carrier_encode.add_argument("--frame", required=True, help="binary input file, or -")
    carrier_encode.add_argument("--output", required=True, help="UTF-8 carrier file, or -")
    carrier_encode.set_defaults(handler=_carrier_encode)

    carrier_decode = subparsers.add_parser(
        "carrier-decode", help="recover a framed message from a qualified real-model carrier"
    )
    carrier_decode.add_argument("address", type=Path)
    carrier_decode.add_argument("--model-root", type=Path, required=True)
    carrier_decode.add_argument("--subject", required=True)
    carrier_decode.add_argument("--carrier", required=True, help="UTF-8 carrier file, or -")
    carrier_decode.add_argument("--output", required=True, help="binary output file, or -")
    carrier_decode.set_defaults(handler=_carrier_decode)
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
