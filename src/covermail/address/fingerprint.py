"""Content-derived Covermail Address identifiers."""

import base64
import hashlib

from covermail.address.canonical import canonical_json, encode_base64url
from covermail.address.schema import Address


def address_digest(address: Address) -> bytes:
    return hashlib.sha256(canonical_json(address)).digest()


def address_id(address: Address) -> bytes:
    return address_digest(address)[:16]


def machine_address_id(address: Address) -> str:
    return encode_base64url(address_id(address))


def human_fingerprint(address: Address) -> str:
    text = base64.b32encode(address_digest(address)).decode("ascii").rstrip("=")
    return " ".join(text[index : index + 4] for index in range(0, len(text), 4))
