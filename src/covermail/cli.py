"""Offline Stage 1 CLI for binary Covermail payload exchange."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import NoReturn

from covermail.address.canonical import canonical_json, read_address_file
from covermail.address.fingerprint import human_fingerprint, machine_address_id
from covermail.address.schema import Address, validate_address
from covermail.crypto.identity import generate_identity
from covermail.crypto.private_store import save_identity, unlock_identity
from covermail.errors import CovermailError
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="covermail",
        description="Covermail v1 Stage 1 binary protocol tools (no generative carrier yet)",
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
