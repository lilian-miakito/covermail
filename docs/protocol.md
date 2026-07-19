# Covermail protocol and implementation specification

Status: **implementation draft for Covermail v1**  
Target implementation: **Python 3.12 + FastAPI, local-only web application**  
Repository: `github.com/lilian-miakito/covermail`  
License target: MIT, using a clean implementation; do not copy GPL source from
`conversation-steganography`.

This document is deliberately more detailed than a conventional protocol
overview. It is the handoff specification for a fresh implementation session.
An implementer should be able to create the repository, write the first
interoperable prototype, and understand the security boundaries without
needing the conversation that produced this document.

The normative words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and
**MAY** are used in the sense of RFC 2119 / RFC 8174.

## 1. Executive summary

Covermail is a stateless, recipient-oriented, generative steganography system.

Alice creates a long-lived recipient identity consisting of:

1. an HPKE private key, which she keeps secret;
2. a public HPKE key;
3. a complete deterministic language-model and token-codec configuration;
4. a cover-writing profile describing language, relationship, tone, and
   constraints;
5. a compatibility self-test proving that the model stack produces the exact
   candidate tokens and arithmetic frequencies expected by Alice.

The public elements form an immutable **Covermail Address**. Alice publishes
that address and verifies its human-readable fingerprint with Bob through an
authenticated channel.

Bob needs only Alice's public address and a compatible local model. For each
secret email, Bob:

1. validates the address and its model self-test;
2. canonicalizes the visible outer subject;
3. compresses and frames the UTF-8 secret message;
4. encrypts the frame using RFC 9180 HPKE Base mode;
5. frames the resulting HPKE bytes;
6. uses arithmetic coding to map those bytes into deterministic language-model
   token choices;
7. returns a normal-looking, single-paragraph outer email body.

Alice receives the visible subject and body. She selects the corresponding
Covermail identity, recomputes the same token candidate distributions,
recovers the HPKE bytes, decrypts them with her private key, and obtains the
secret email.

There is no conversational chain and no shared secret. Each message is an
independent single-shot encryption. Anyone holding Alice's public address can
create a valid message to Alice. V1 deliberately does not authenticate Bob.

## 2. Product statement

The intended user statement is:

> Alice publishes a Covermail Address. Bob imports it, writes a short private
> email and a plausible visible subject, and receives an ordinary-looking
> cover email to send through any normal email provider. Alice pastes the exact
> visible subject and body into her local Covermail application and recovers
> the private email.

The product MUST describe itself as experimental camouflage providing
plausible deniability. It MUST NOT claim information-theoretic steganographic
security, guaranteed undetectability, endpoint security, anonymity, or
forward secrecy.

## 3. Goals and non-goals

### 3.1 Goals

V1 aims to provide:

- confidentiality of the hidden plaintext against anyone who does not hold
  Alice's HPKE private key;
- a stateless send and receive protocol at the message layer;
- anonymous-sender public-key encryption: possession of the public address is
  sufficient to send;
- deterministic recovery when Alice and Bob use compatible model stacks;
- a visible carrier that resembles one ordinary personal email paragraph;
- a local-only application with no Covermail server and no telemetry;
- exact, versioned, testable wire formats;
- early compatibility failure before Bob sends a carrier;
- a public, inspectable implementation with pinned dependencies and fixtures.

### 3.2 Non-goals

V1 does not provide:

- sender authentication or non-repudiation;
- replay detection without optional local history;
- ordering, delivery receipts, or mailbox synchronization;
- forward secrecy after compromise of Alice's long-lived private key;
- protection when Alice's or Bob's operating system is compromised during use;
- transport metadata protection, including sender, recipient, time, IP address,
  subject, and message length;
- robust recovery after arbitrary email-body modification;
- support for HTML carriers, attachments, signatures, quoted replies, or rich
  MIME bodies;
- efficient hiding of arbitrarily long messages;
- post-quantum confidentiality in the initial v1 suite;
- a remotely hosted web application.

## 4. Threat model

### 4.1 Adversary capabilities

The design assumes an adversary may:

- operate or fully compromise the email provider;
- retain all outer messages indefinitely;
- inspect visible body text with human or automated classifiers;
- know that Covermail exists and possess its source code;
- obtain Alice's public address and exact model artifacts;
- decode the generative layer if the carrier is recognized as Covermail;
- alter, truncate, reorder, replay, or delete outer messages;
- replace a public address distributed through an unauthenticated channel;
- submit malformed addresses and carriers to the local application.

The adversary is not assumed to:

- control Alice's or Bob's local machine at the moment of encryption or
  decryption;
- know Alice's private-key passphrase or extract her unlocked private key from
  memory;
- break the selected HPKE ciphersuite;
- break SHA-256 collision or second-preimage resistance.

### 4.2 Security if the generative layer is detected

The language-model layer is not the confidentiality boundary. A knowledgeable
observer may reconstruct the complete binary Covermail envelope. Confidentiality
must still rest on HPKE.

If an observer extracts an envelope, the observer learns at least:

- that the carrier is probably Covermail;
- the Covermail protocol version;
- a 128-bit address identifier;
- the HPKE ciphertext length and therefore an approximation of plaintext
  length.

The observer still must not recover the inner plaintext without Alice's
private key.

### 4.3 Meaning of plausible deniability

Plausible deniability in v1 is limited and must be stated precisely:

- the outer text has an ordinary semantic interpretation unrelated to the
  inner text;
- HPKE Base mode does not cryptographically identify Bob;
- anyone with Alice's public address could have produced a valid carrier;
- Alice cannot use a digital signature from the message to prove authorship by
  Bob.

This statement concerns the hidden Covermail layer only. Ordinary email
metadata, account access logs, DKIM signatures, device evidence, or Bob's own
records may independently attribute the visible outer email.

V1 does **not** implement deniable encryption with alternate keys or alternate
plaintexts. If Alice discloses her private key and the exact public address, a
recognized carrier decrypts to one authenticated plaintext.

### 4.4 Public-address substitution

Public-key encryption does not solve key distribution. If Mallory replaces
Alice's entire public address with Mallory's key and a compatible configuration,
Bob will encrypt to Mallory.

The UI MUST display a human-readable address fingerprint. Alice and Bob MUST
verify it through an authenticated channel, for example in person, a QR code,
or a previously authenticated messenger. Self-signing the address with a key
contained in the same unverified address would not solve substitution.

## 5. Roles and state

### 5.1 Alice, the recipient

Alice owns one or more Covermail identities. Each identity consists of:

- one immutable public address;
- one X25519 private key corresponding to the address public key;
- optional local replay/history metadata, which is not needed to decrypt;
- local access to the exact model artifacts specified by the address.

Changing a cryptographic suite, public key, model, tokenizer, codec parameter,
prompt template, or cover profile creates a new address and fingerprint.

### 5.2 Bob, the sender

Bob imports Alice's public address. Bob has no Covermail private key requirement
in v1 and creates no sender identity. Bob MAY retain the imported address and
generated-carrier history locally, but neither is required by the wire protocol.

### 5.3 Stateless semantics

Each message is independently encrypted with a fresh HPKE ephemeral key. The
prompt MUST NOT depend on previous hidden messages or previous Covermail state.
The prompt MAY depend on visible information delivered with the same outer
email, specifically the canonical outer subject.

Alice's private key is persistent identity state. "Stateless" describes the
message protocol, not the absence of any local key material.

## 6. Normative protocol constants

The following constants define Covermail v1:

| Name | Value |
|---|---:|
| `PROTOCOL_VERSION` | `1` |
| `ADDRESS_FORMAT` | `"covermail-address"` |
| `ADDRESS_VERSION` | `1` |
| `INNER_VERSION` | `1` |
| `CODEC_ID` | `"cm-arithmetic-v1"` |
| `HPKE_INFO_LABEL` | ASCII `"covermail/hpke/v1\x00"` |
| `KEM` | DHKEM(X25519, HKDF-SHA256) |
| `KDF` | HKDF-SHA256 |
| `AEAD` | AES-128-GCM |
| `ADDRESS_DIGEST` | SHA-256 over canonical public address |
| `ADDRESS_ID_LENGTH` | 16 bytes |
| `ARITHMETIC_BITS` | 32 |
| `FREQUENCY_TOTAL` | 32768 |
| `LOGIT_SCALE` | 1024 |
| `WEIGHT_SCALE` | 16777216 (`2^24`) |
| `MAX_CODING_SYMBOL_FREQUENCY` | 24576 (75% of total) |
| `MAX_CONSECUTIVE_BRIDGE_TOKENS` | 32 |
| `MAX_PUBLIC_ADDRESS_BYTES` | 1 MiB |
| `MAX_SECRET_UTF8_BYTES` | 65535 protocol hard limit |
| `DEFAULT_UI_SECRET_BYTES` | 512 warning budget |
| `MAX_STEGO_PAYLOAD_BYTES` | 131072 protocol hard limit |
| `MAX_FINISH_TOKENS` | 128 hard limit |
| `DEFAULT_FINISH_TOKENS` | 32 |
| `MAX_MODEL_CANDIDATES` | 4096 |
| `MAX_CARRIER_TOKENS` | implementation-derived, hard-capped |

The initial implementation SHOULD impose much smaller operational limits than
the protocol hard limits. Generating a carrier for 64 KiB of plaintext is not
practical; the high limit only makes parsers and allocation behavior explicit.

## 7. Byte, text, integer, and JSON conventions

### 7.1 Bytes and text

- All protocol text is Unicode encoded as strict UTF-8.
- Invalid UTF-8 MUST be rejected.
- Protocol labels are ASCII bytes, not locale-dependent strings.
- Base64url values use the URL-safe alphabet without `=` padding.
- Hashes are lowercase hexadecimal unless the schema explicitly says
  base64url.

Strict base64url helpers:

```python
import base64
import binascii


def encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode_base64url(text: str) -> bytes:
    try:
        encoded = text.encode("ascii", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError("base64url must be ASCII") from error
    if b"=" in encoded or len(encoded) % 4 == 1:
        raise ValueError("non-canonical base64url length or padding")
    padding = b"=" * ((4 - len(encoded) % 4) % 4)
    try:
        value = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
    except binascii.Error as error:
        raise ValueError("invalid base64url") from error
    if encode_base64url(value) != text:
        raise ValueError("non-canonical base64url")
    return value
```

### 7.2 Unsigned varint

Covermail uses canonical unsigned LEB128 for lengths:

```python
def encode_uvarint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative uvarint")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def decode_uvarint(data: bytes, offset: int = 0, *, max_bytes: int = 5) -> tuple[int, int]:
    value = 0
    shift = 0
    for index in range(max_bytes):
        position = offset + index
        if position >= len(data):
            raise EOFError("incomplete uvarint")
        byte = data[position]
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            encoded = encode_uvarint(value)
            consumed = index + 1
            if data[offset:offset + consumed] != encoded:
                raise ValueError("non-canonical uvarint")
            return value, consumed
        shift += 7
    raise ValueError("uvarint exceeds limit")
```

Parsers MUST reject overlong encodings and lengths exceeding the relevant hard
limit before allocating buffers.

### 7.3 Canonical public-address JSON

The address schema deliberately forbids floating-point values. Allowed JSON
types are objects, arrays, strings, integers, booleans, and null. Object member
names defined by v1 are ASCII.

Canonical bytes are produced with:

```python
import json


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
```

Before canonicalization, the implementation MUST recursively reject Python
`float` values and integers outside signed 64-bit range. Strings MUST be valid
Unicode and normalized only where the field definition explicitly requires
normalization. The address hash is over the semantic parsed object rendered by
the exact function above, not over the original file whitespace.

This restricted profile is intentionally simpler than accepting arbitrary
JSON number semantics. A future version may adopt RFC 8785 JCS in full, but v1
interoperability is defined by the function above.

## 8. The Covermail Address

### 8.1 Top-level schema

A public address is one JSON object:

```json
{
  "format": "covermail-address",
  "version": 1,
  "recipient": {
    "label": "Alice",
    "hpke_public_key": "BASE64URL_32_RAW_X25519_BYTES"
  },
  "hpke": {
    "kem": "DHKEM_X25519_HKDF_SHA256",
    "kdf": "HKDF_SHA256",
    "aead": "AES_128_GCM",
    "mode": "BASE"
  },
  "model": {
    "backend": "mlx-lm",
    "model_id": "mlx-community/Llama-3.2-3B-Instruct-4bit",
    "revision": "IMMUTABLE_COMMIT_OR_SNAPSHOT_ID",
    "artifacts": [
      {
        "path": "config.json",
        "size": 0,
        "sha256": "LOWERCASE_HEX_SHA256"
      }
    ],
    "runtime": {
      "profile": "darwin-arm64-mlx-v1",
      "python_version": "EXACT_PATCH_VERSION",
      "packages": {
        "mlx": "PINNED_VERSION",
        "mlx-lm": "PINNED_VERSION",
        "numpy": "PINNED_VERSION"
      },
      "logits_dtype": "float32",
      "trust_remote_code": false
    }
  },
  "codec": {
    "id": "cm-arithmetic-v1",
    "top_n": 256,
    "candidate_pool_multiplier": 8,
    "frequency_total": 32768,
    "logit_scale": 1024,
    "temperature_milli": 1000,
    "length_bias_milli": 100,
    "finish_tokens": 32,
    "visible_filter": "cm-visible-email-v1",
    "prompt_template": "cm-email-one-paragraph-v1",
    "self_test": {
      "steps": 4,
      "path_indices": [0, 1, 255, 0],
      "expected_sha256": "LOWERCASE_HEX_SHA256"
    }
  },
  "cover": {
    "language": "fr-FR",
    "relationship": "deux amis proches",
    "tone": "familier, calme et naturel",
    "persona_sender": "une personne ordinaire écrivant un bref email",
    "persona_recipient": "un ami de longue date",
    "standing_context": "Ils échangent occasionnellement des nouvelles du quotidien.",
    "max_sentences": 4,
    "max_questions": 1,
    "max_visible_characters": 4000
  }
}
```

The actual generated address MUST contain correct artifact sizes and hashes,
not the placeholders above.

### 8.2 Address validation

An importer MUST:

1. reject files larger than `MAX_PUBLIC_ADDRESS_BYTES`;
2. parse strict JSON with duplicate-object-key detection;
3. reject unknown fields at every schema level in v1;
4. reject missing or incorrectly typed fields;
5. reject floats and out-of-range integers;
6. require exact `format` and `version` values;
7. require the exact v1 HPKE suite and Base mode;
8. decode `hpke_public_key` and require exactly 32 bytes;
9. validate the raw bytes as an X25519 public key through `cryptography`;
10. reject executable model configuration, remote Python code, URL schemes
    other than explicitly supported model registries, and local absolute paths;
11. enforce all codec hard limits;
12. require `frequency_total == 32768` and `logit_scale == 1024` for v1;
13. validate BCP-47-like language syntax conservatively;
14. constrain all free-text cover fields to reasonable UTF-8 byte lengths;
15. calculate the address digest and display its fingerprint;
16. verify local model artifacts and execute the self-test before allowing send.

V1 field limits:

| Field | Constraint |
|---|---|
| `recipient.label` | 1..128 UTF-8 bytes; display-only, untrusted |
| `model.model_id` | 1..256 ASCII bytes; qualified registry syntax only |
| `model.revision` | 7..128 lowercase hexadecimal characters for the initial Hugging Face profile |
| `model.artifacts` | 1..256 entries |
| artifact `path` | 1..512 UTF-8 bytes and safe relative path rules |
| artifact `size` | 0..`2^40-1` |
| artifact `sha256` | exactly 64 lowercase hexadecimal characters |
| `codec.top_n` | 2..512 |
| `candidate_pool_multiplier` | 1..16 |
| `top_n * candidate_pool_multiplier` | at most 4096 |
| `temperature_milli` | 100..2000 |
| `length_bias_milli` | 0..1000 |
| `finish_tokens` | 0..128 |
| each free-text cover field | 0..512 UTF-8 bytes, except required fields must be non-empty |
| `cover.max_sentences` | 1..8 |
| `cover.max_questions` | 0..2 and no greater than `max_sentences` |
| `cover.max_visible_characters` | 200..20000 |

The initial curated UI MAY expose a narrower subset, for example fixed
`top_n`, temperature, and runtime profile. Parsing must still enforce the full
wire limits above.

JSON duplicate keys MUST be rejected rather than silently taking the last
value. A reference loader can use `object_pairs_hook`:

```python
import json


def reject_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_address_json(raw: bytes) -> dict[str, object]:
    if len(raw) > 1 << 20:
        raise ValueError("address too large")
    text = raw.decode("utf-8", errors="strict")
    value = json.loads(text, object_pairs_hook=reject_duplicate_object)
    if not isinstance(value, dict):
        raise ValueError("address must be an object")
    return value
```

### 8.3 Address digest, address ID, and fingerprint

```python
import base64
import hashlib


def address_digest(address: dict[str, object]) -> bytes:
    return hashlib.sha256(canonical_json(address)).digest()


def address_id(address: dict[str, object]) -> bytes:
    return address_digest(address)[:16]


def machine_address_id(address: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(address_id(address)).rstrip(b"=").decode("ascii")


def human_fingerprint(address: dict[str, object]) -> str:
    text = base64.b32encode(address_digest(address)).decode("ascii").rstrip("=")
    return " ".join(text[i:i + 4] for i in range(0, len(text), 4))
```

The UI MUST display the full 256-bit human fingerprint for verification. It
MAY display the 128-bit address ID for ordinary selection, but MUST NOT present
that shorter ID as equivalent to full fingerprint verification.

### 8.4 Immutability and updates

The address digest binds the complete cryptographic, model, codec, and cover
configuration. Any field change creates a different address.

V1 has no signed address-update protocol. Alice distributes a new address and
verifies its new fingerprint. An old private identity remains able to decode
old messages as long as its artifacts remain available.

### 8.5 Model artifact entries

Artifact paths MUST be relative POSIX paths without `..`, an empty component,
a leading slash, a drive letter, or a NUL byte. Symlinks MUST NOT be followed
when verifying an address-controlled artifact tree.

At minimum the manifest SHOULD cover:

- model configuration;
- tokenizer model/data;
- tokenizer configuration and special-token mapping;
- every weight shard;
- generation or chat-template configuration used by the adapter.

Hashing only filenames and sizes is insufficient. Every consumed file MUST be
hashed by SHA-256.

Runtime versions are exact versions, including the Python patch release. The
`profile` is a source-controlled adapter identifier that fixes relevant backend
settings and the claimed operating-system/architecture class. Importers MUST
not infer compatibility from a similar package version or model marketing name;
the self-test remains authoritative.

## 9. Private identity storage

### 9.1 Key generation

The implementation MUST use the operating system CSPRNG through
`cryptography`:

```python
from cryptography.hazmat.primitives.asymmetric import x25519


private_key = x25519.X25519PrivateKey.generate()
public_key = private_key.public_key()
```

The public address stores the 32-byte raw public key:

```python
from cryptography.hazmat.primitives import serialization


public_raw = public_key.public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)
```

### 9.2 Private-key file

The private key MUST NOT be stored as unencrypted raw bytes. The reference
implementation SHOULD store encrypted PKCS#8 PEM using
`BestAvailableEncryption`:

```python
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.BestAvailableEncryption(passphrase),
)
```

The identity directory SHOULD be:

```text
~/.covermail/identities/<address-id>/
  address.json
  private-key.pem
  metadata.json
```

Directories MUST be created with mode `0700` and private files with mode
`0600` on POSIX systems. The passphrase MUST NOT be persisted, logged, placed
in command-line arguments, or returned by an API. The unlocked key SHOULD be
held only for the active operation and released afterwards. Python cannot
guarantee complete zeroization; the documentation must not claim otherwise.

`BestAvailableEncryption` is an acceptable demonstrator storage mechanism, not
a frozen Covermail wire format. Before a security-oriented release, the project
must document and test the actual PKCS#8 password-encryption parameters supplied
by the pinned `cryptography` version and decide whether an OS keychain or a
versioned memory-hard passphrase container is required for stolen-file
resistance. A weak user passphrase remains vulnerable to offline guessing.

OS keychain integration MAY be added later. It is not part of the wire
protocol.

## 10. Inner plaintext frame

### 10.1 Purpose

The inner frame is encrypted by HPKE. It identifies the Covermail plaintext
format, carries a random message ID, records the original UTF-8 byte length,
and indicates whether raw DEFLATE compression was used.

### 10.2 Binary layout

```text
offset  size       field
0       1          INNER_VERSION = 0x01
1       1          flags
2       16         random message_id
18      varint     original UTF-8 byte length
...     remaining  body (raw UTF-8 or raw-DEFLATE bytes)
```

Flag bits:

- bit 0: body uses raw DEFLATE (`wbits=-15`);
- bits 1 through 7: reserved and MUST be zero.

The `message_id` MUST contain 16 fresh random bytes from `secrets.token_bytes`.
It is encrypted and is not sender authentication. A recipient MAY store
message IDs to warn about replay; doing so is optional state outside the core
protocol.

### 10.3 Compression

```python
import secrets
import zlib


INNER_VERSION = 1
FLAG_DEFLATE = 0x01
MAX_SECRET_UTF8_BYTES = 65535


def pack_inner(text: str) -> bytes:
    plaintext = text.encode("utf-8", errors="strict")
    if len(plaintext) > MAX_SECRET_UTF8_BYTES:
        raise ValueError("secret message exceeds protocol limit")

    compressor = zlib.compressobj(level=9, wbits=-15)
    compressed = compressor.compress(plaintext) + compressor.flush()
    if len(compressed) < len(plaintext):
        flags = FLAG_DEFLATE
        body = compressed
    else:
        flags = 0
        body = plaintext

    return (
        bytes([INNER_VERSION, flags])
        + secrets.token_bytes(16)
        + encode_uvarint(len(plaintext))
        + body
    )
```

The compressor output does not need to be deterministic across senders because
only Bob compresses that message and Alice only decompresses it. It MUST use
raw DEFLATE, not a zlib or gzip wrapper.

### 10.4 Safe unpacking

The decompressor MUST enforce the declared original length while streaming and
MUST reject trailing compressed data, premature end, and output beyond the
hard limit. It MUST NOT call an unbounded one-shot decompression on attacker-
controlled bytes.

Reference behavior:

```python
def unpack_inner(frame: bytes) -> tuple[bytes, str]:
    if len(frame) < 19:
        raise ValueError("inner frame too short")
    version, flags = frame[0], frame[1]
    if version != INNER_VERSION:
        raise ValueError("unsupported inner version")
    if flags & ~FLAG_DEFLATE:
        raise ValueError("reserved inner flags are set")

    message_id = frame[2:18]
    original_len, consumed = decode_uvarint(frame, 18, max_bytes=3)
    if original_len > MAX_SECRET_UTF8_BYTES:
        raise ValueError("declared plaintext exceeds limit")
    body = frame[18 + consumed:]

    if flags & FLAG_DEFLATE:
        decompressor = zlib.decompressobj(wbits=-15)
        plaintext = decompressor.decompress(body, original_len + 1)
        plaintext += decompressor.flush(original_len + 1 - len(plaintext))
        if len(plaintext) > original_len:
            raise ValueError("decompression exceeded declared size")
        if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
            raise ValueError("malformed or trailing compressed stream")
    else:
        plaintext = body

    if len(plaintext) != original_len:
        raise ValueError("plaintext length mismatch")
    text = plaintext.decode("utf-8", errors="strict")
    return message_id, text
```

The exact zlib streaming code MUST receive adversarial tests; APIs differ
slightly across Python versions. The normative requirement is bounded output
and exact end-of-stream validation, not blind use of the illustrative snippet.

## 11. HPKE encryption

### 11.1 Library requirement

The reference implementation targets `cryptography==49.0.0` or a later version
explicitly qualified by tests. Version 49 exposes RFC 9180 single-shot HPKE via
`cryptography.hazmat.primitives.hpke.Suite`.

The implementation MUST NOT implement X25519, HKDF, the HPKE key schedule,
AES-GCM, or nonce construction itself.

References:

- RFC 9180: <https://www.rfc-editor.org/rfc/rfc9180.html>
- pyca/cryptography HPKE API:
  <https://cryptography.io/en/49.0.0/hazmat/primitives/hpke/>

### 11.2 Fixed ciphersuite

```python
from cryptography.hazmat.primitives.hpke import AEAD, KDF, KEM, Suite


HPKE_SUITE = Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.AES_128_GCM)
```

V1 does not negotiate algorithms. Addresses declaring another suite MUST be
rejected. Fixed algorithms avoid downgrade logic and reduce envelope overhead.

### 11.3 HPKE context information

The library's single-shot API accepts `info` and returns `enc || ct`. Covermail
binds the operation to the complete address and public outer envelope header:

```text
hpke_info = HPKE_INFO_LABEL || address_digest || outer_header
```

where:

```text
outer_header = PROTOCOL_VERSION (1 byte) || address_id (16 bytes)
```

Because `address_digest` is 32 bytes and `address_id` is its first 16 bytes,
the shorter transmitted ID is cryptographically bound to the full address
known by Alice and Bob.

### 11.4 Encryption and decryption snippets

```python
from cryptography.hazmat.primitives.asymmetric import x25519


HPKE_INFO_LABEL = b"covermail/hpke/v1\x00"
PROTOCOL_VERSION = 1


def outer_header(address: dict[str, object]) -> bytes:
    return bytes([PROTOCOL_VERSION]) + address_id(address)


def hpke_info(address: dict[str, object]) -> bytes:
    return HPKE_INFO_LABEL + address_digest(address) + outer_header(address)


def encrypt_inner(address: dict[str, object], inner: bytes) -> bytes:
    raw = decode_base64url(address["recipient"]["hpke_public_key"])
    public_key = x25519.X25519PublicKey.from_public_bytes(raw)
    # cryptography generates a fresh ephemeral key for every call.
    return HPKE_SUITE.encrypt(inner, public_key, info=hpke_info(address))


def decrypt_inner(
    address: dict[str, object],
    private_key: x25519.X25519PrivateKey,
    hpke_blob: bytes,
) -> bytes:
    return HPKE_SUITE.decrypt(hpke_blob, private_key, info=hpke_info(address))
```

`decrypt` authentication failures MUST be mapped to one generic user-facing
error. The UI MUST NOT distinguish wrong private key, modified ciphertext,
wrong address profile, or malformed authenticated plaintext until after HPKE
authentication succeeds.

### 11.5 Size overhead

For the v1 suite, the HPKE result contains a 32-byte X25519 encapsulated key and
an AES-GCM ciphertext with a 16-byte authentication tag. The minimum HPKE
overhead is therefore 48 bytes in addition to the inner frame. The UI budget
must account for this before launching model generation.

## 12. Outer binary payload and stego frame

### 12.1 Outer payload

The bytes embedded by the generative codec are:

```text
outer_payload = outer_header || hpke_blob
```

Layout:

```text
offset  size       field
0       1          PROTOCOL_VERSION = 0x01
1       16         address_id = SHA-256(canonical_address)[0:16]
17      remaining  HPKE enc || ct
```

The minimum valid HPKE blob is larger than 48 bytes because the authenticated
inner frame has mandatory fields. Parsers MUST nevertheless validate lengths
through the HPKE and inner-frame layers rather than relying on one magic
minimum.

### 12.2 Stego frame

The exact byte stream fed to the arithmetic bit source is:

```text
stego_frame = uvarint(len(outer_payload)) || outer_payload
```

The length prefix is not encryption metadata exposed in visible text; it is
itself hidden through token choices. It allows deterministic arithmetic-stream
termination before HPKE is attempted.

The decoder MUST reject:

- an incomplete or non-canonical length;
- a declared length above `MAX_STEGO_PAYLOAD_BYTES`;
- fewer recovered bits than the declared frame;
- non-sentinel confirmed bits after the declared frame boundary;
- an unsupported protocol version;
- an address ID different from the selected address.

## 13. Visible email transport profile

### 13.1 V1 carrier form

V1 supports one carrier form:

- a visible email subject supplied by Bob and delivered normally;
- a generated body containing exactly one paragraph;
- no leading or trailing whitespace;
- no CR, LF, or tab inside the body;
- no HTML dependency;
- no automatic signature inside the copied carrier;
- no quoted message or reply prefix inside the copied carrier.

The subject does not carry hidden bits. It is deterministic public prompt
context. Alice must supply the exact visible subject to decode, but the subject
is canonicalized as described below.

### 13.2 Subject canonicalization

```python
import re
import unicodedata


def canonical_subject(subject: str) -> str:
    if "\x00" in subject or "\r" in subject or "\n" in subject:
        raise ValueError("invalid subject control character")
    normalized = unicodedata.normalize("NFC", subject)
    normalized = re.sub(r"[\t ]+", " ", normalized).strip(" ")
    if not normalized:
        raise ValueError("subject is empty")
    if len(normalized.encode("utf-8")) > 256:
        raise ValueError("subject exceeds 256 UTF-8 bytes")
    return normalized
```

Reply prefixes such as `Re:` are not removed in v1. Alice and Bob must provide
the same visible subject after the above canonicalization.

### 13.3 Carrier-body handling

The body is tokenizer-sensitive and MUST NOT be Unicode-normalized, case-folded,
trimmed arbitrarily, have spaces collapsed, or have punctuation replaced.

The paste UI MAY remove exactly one terminal email line ending (`\r\n`, `\n`,
or `\r`) that is clearly introduced by the text area. It MUST then require:

- no remaining CR, LF, or tab;
- no leading or trailing Unicode whitespace;
- valid UTF-8 when serialized;
- character and token counts below configured hard limits.

Any other change must result in failure. Later protocol versions may add an
error-correcting transport layer, but v1 does not silently guess edits.

### 13.4 Operational email guidance

The UI must tell Bob:

- send as plain text when possible;
- disable automatic signature insertion for the carrier block;
- copy only the generated body;
- do not edit punctuation, spacing, capitalization, or accents;
- do not let an assistant rewrite the message;
- retain the original generated carrier locally until Alice confirms receipt.

The UI must tell Alice to paste only the exact carrier paragraph, excluding
email signatures, quoted history, and client UI labels.

## 14. Cover profile and prompt construction

### 14.1 Public cover profile

The `cover` object is public and immutable. Alice controls the general social
setting and language. Bob controls only the visible outer subject and secret
message. The secret plaintext MUST NOT be included in the model prompt.

Free-text cover fields are treated only as data. They MUST NOT be evaluated as
templates, Python, Jinja, shell, URLs, or model code.

### 14.2 Prompt template `cm-email-one-paragraph-v1`

The logical chat messages are:

```text
SYSTEM:
You write one plausible personal email paragraph in {language}. The writer and
reader are {relationship}. Tone: {tone}. Writer persona: {persona_sender}.
Reader persona: {persona_recipient}. Shared background: {standing_context}.
Write only the email body. Stay on the visible subject. Use at most
{max_sentences} sentences and {max_questions} question. Do not use a greeting,
signature, list, label, metadata, formatting, line break, or mention of these
instructions. Never mention hidden data, encryption, prompts, models, senders,
recipients, or analysis.

USER:
Visible email subject: {canonical JSON string of canonical_subject}
Write the body now.
```

The implementation MUST build a structured message list and use the pinned
tokenizer's chat template when the model adapter declares chat-template
support:

```python
messages = [
    {"role": "system", "content": system_text},
    {"role": "user", "content": user_text},
]
prompt_text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
)
```

The model manifest MUST include the hash of every tokenizer/chat-template file
that affects rendering. The compatibility self-test hashes the rendered prompt
and detects a different template.

For a non-chat model, a future named prompt adapter may define direct text.
V1 implementations MUST NOT improvise an adapter based only on model name.

### 14.3 Prompt escaping

The subject and cover values are length-bounded and rendered as JSON string
literals where inserted into prose. Model-specific control-token substrings,
including `<|`, MUST be replaced by a visibly separated form before prompt
rendering. This is a naturalness defense, not a confidentiality boundary.

The prompt builder MUST be a pure deterministic function of:

- address cover fields;
- address prompt-template ID;
- canonical visible subject;
- pinned tokenizer/chat template.

It MUST NOT read current time, hostname, user locale, previous carriers,
randomness, or hidden plaintext.

## 15. Deterministic model interface

### 15.1 Abstract interface

```python
from typing import Protocol, Sequence


class ModelCandidate(Protocol):
    token_id: int
    logit: float
    token_text: str


class LanguageModel(Protocol):
    def tokenize(self, text: str) -> list[int]: ...
    def detokenize(self, token_ids: Sequence[int]) -> str: ...
    def next_logits(self, context_ids: Sequence[int]) -> "ArrayLike": ...
    def special_token_ids(self) -> set[int]: ...
    def runtime_fingerprint(self) -> dict[str, object]: ...
```

Generation MUST NOT call a sampling API. It directly obtains next-token logits
and chooses a token through the arithmetic codec.

### 15.2 Model loading rules

The loader MUST:

- resolve only the exact `model_id` and immutable `revision` from the address;
- verify every artifact size and SHA-256 before use;
- set `trust_remote_code=False`;
- avoid arbitrary address-supplied filesystem paths;
- accept model weights only in explicitly qualified non-executable formats such
  as safetensors; reject pickle-backed `.bin`, `.pt`, and `.pth` weights;
- force safe-weight loading (`use_safetensors=True` or backend equivalent);
- load the exact pinned backend and framework versions;
- put the model in inference/evaluation mode;
- disable dropout and gradients;
- request deterministic algorithms where supported;
- cast exported logits to IEEE-754 float32 before candidate quantization;
- reject non-finite logits;
- run the address self-test before enabling encode or decode.

Model download is a distinct, user-confirmed operation. Sending and receiving
must work offline after artifacts are prepared.

### 15.3 Reproducibility limitation

Exact weights and versions are necessary but may not be sufficient. Different
hardware kernels can produce slightly different logits, candidate rankings, or
ties. Covermail therefore treats the model stack as a protocol implementation,
not an interchangeable semantic model.

An address is usable on a device only if its self-test passes. Passing the
self-test reduces but cannot mathematically prove compatibility for every
possible generation prefix. Cross-device carrier fixtures are mandatory before
declaring a model/runtime profile supported.

## 16. Model compatibility self-test

### 16.1 Purpose

The self-test allows Bob to discover incompatibility before sending an
undecodable carrier. It tests prompt rendering, tokenization, logits,
candidate filtering, logit quantization, frequency construction, and chosen
prefix evolution.

### 16.2 Test input

The fixed v1 self-test subject is:

```text
Covermail deterministic compatibility test
```

The subject is intentionally protocol-defined and is passed through the same
canonicalization and prompt builder as an ordinary subject.

### 16.3 Test path

Starting with an empty visible prefix, execute `steps` states. At each state:

1. compute the final `top_n` candidate list and integer frequency counts;
2. append to a byte transcript:
   - state index as unsigned 32-bit big-endian;
   - SHA-256 of the rendered prompt at state zero, otherwise 32 zero bytes;
   - candidate count as unsigned 16-bit big-endian;
   - for each candidate in order, signed 32-bit big-endian token ID followed by
     unsigned 16-bit big-endian frequency count;
3. select the candidate at `path_indices[state]`;
4. append its token ID to the visible prefix and continue.

Finally compute SHA-256 of the transcript. It MUST equal
`codec.self_test.expected_sha256`.

The path indices MUST have length equal to `steps`, each must be less than
`top_n`, and the initial implementation MUST require exactly four steps and
the v1 path `[0, 1, top_n - 1, 0]`.

### 16.4 Alice address creation

Alice's application creates the address in two phases:

1. build the address object with `expected_sha256` temporarily set to 64 ASCII
   zero characters;
2. run the self-test, write the result into `expected_sha256`, validate the
   complete address, and compute the final address digest.

The prompt MUST NOT include the address digest, address ID, or self-test hash,
avoiding a recursive dependency.

## 17. Candidate construction

### 17.1 Candidate-pool size

```text
requested = top_n * candidate_pool_multiplier
```

The product MUST satisfy:

```text
2 <= top_n
requested <= MAX_MODEL_CANDIDATES
top_n < FREQUENCY_TOTAL
```

The backend obtains the full vocabulary logit vector, casts each finite value
to float32, applies the v1 integer logit quantizer without length penalty, and
orders non-special token IDs by quantized logit descending then token ID
ascending. It takes the first `requested` IDs as the candidate pool. It MUST
NOT rely on an unspecified GPU `topk` tie order or `argpartition` boundary.

Copy-safe and visible filtering are then applied to that pool. If fewer than
`top_n` survive, generation fails. An adapter MAY use an optimized top-k
primitive only after tests prove that it returns the same pool, including all
quantized-score boundary ties resolved by token ID.

### 17.2 Copy-safe property

For every candidate token `t`, with current visible token prefix `V`, require:

```text
tokenize(detokenize(V || [t])) == V || [t]
```

The complete prefix is normative. An implementation MAY optimize by proving a
bounded-tail check equivalent for a qualified tokenizer, but the reference and
test implementation should check the full sequence until profiling justifies
an adapter-specific optimization.

This property prevents a copied visible string from retokenizing into different
IDs at Alice.

### 17.3 Visible filter `cm-visible-email-v1`

A candidate is rejected if any condition holds:

- token ID is special;
- token text is empty;
- token text contains CR, LF, tab, NUL, or a Unicode control/surrogate/private-
  use/unassigned code point;
- token text contains `<|` or `|>`;
- token text contains markup-heavy characters from the fixed set
  ``{}`[]<>\\^~``;
- after trimming ASCII spaces, it contains neither a Unicode letter nor one of
  the ordinary punctuation characters `.,!?;:'"-()`;
- its single-token text cannot participate in a copy-safe prefix;
- its normalized whole word is in the fixed protocol vocabulary blacklist.

The blacklist MUST be versioned in source and shared by all implementations.
Changing it requires a new codec ID. V1 normalization and vocabulary are:

```python
import unicodedata


META_WORDS_V1 = frozenset({
    "analysis", "assistant", "example", "format", "input", "instruction",
    "instructions", "message", "messages", "metadata", "model", "note",
    "output", "prompt", "prompts", "recipient", "recipients", "response",
    "role", "sender", "system", "timestamp", "token", "tokens",
    "transcript", "user",
    "analyse", "assistant", "exemple", "format", "instruction",
    "instructions", "message", "messages", "metadonnee", "metadonnees",
    "modele", "note", "prompt", "reponse", "role", "systeme", "jeton",
    "jetons", "transcription", "utilisateur",
})


def normalized_visible_word(token_text: str) -> str:
    text = unicodedata.normalize("NFKD", token_text).casefold()
    text = "".join(character for character in text if not unicodedata.combining(character))
    return text.strip(" .,!?:;'\"-_()")
```

The French entries are deliberately stored without diacritics because NFKD
normalization removes combining marks. An ordinary token containing more than
one whitespace-separated word is compared as one complete normalized string;
the blacklist is not applied as a substring search.

### 17.4 Quantized candidate score

Raw logits are not used directly after pool retrieval. For each candidate:

1. cast to float32;
2. convert that exact Python float value to `Decimal`;
3. multiply by `LOGIT_SCALE`;
4. round to nearest integer, ties to even;
5. subtract a deterministic visible-character length penalty.

```python
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import numpy as np


LOGIT_SCALE = 1024


def div_round_half_even(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("this helper expects a non-negative ratio")
    quotient, remainder = divmod(numerator, denominator)
    doubled = remainder * 2
    if doubled > denominator or (doubled == denominator and quotient % 2):
        quotient += 1
    return quotient


def quantize_logit(value: float) -> int:
    finite32 = float(np.float32(value))
    if not math.isfinite(finite32):
        raise ValueError("non-finite model logit")
    with localcontext() as context:
        context.prec = 50
        scaled = Decimal.from_float(finite32) * LOGIT_SCALE
        return int(scaled.to_integral_value(rounding=ROUND_HALF_EVEN))


def adjusted_score(logit: float, token_text: str, length_bias_milli: int) -> int:
    visible_characters = len(token_text)
    penalty_numerator = length_bias_milli * LOGIT_SCALE * visible_characters
    penalty = div_round_half_even(penalty_numerator, 1000)
    return quantize_logit(logit) - penalty
```

`len(token_text)` means Python Unicode code points. All implementations must
match that definition for v1.

### 17.5 Final order

After copy-safe and visible filtering, candidates are ordered by:

1. adjusted quantized score descending;
2. token ID ascending as deterministic tie-breaker.

Take the first `top_n`. Fewer than `top_n` passing candidates is an error. The
same ordered list is used by frequency construction, arithmetic symbols,
self-tests, sender, and receiver.

## 18. Deterministic frequency table

### 18.1 Requirements

The arithmetic table contains one positive integer count per final candidate.
Counts MUST sum exactly to `FREQUENCY_TOTAL`. No symbol may have zero count.

Floating-point `exp` results MUST NOT be normalized directly because tiny
platform differences can move an integer rounding boundary. V1 first quantizes
logits and then uses Python `Decimal` with fixed precision and rounding.

### 18.2 Weight construction

Let `q_i` be adjusted integer scores and `q_max = max(q_i)`. Let
`temperature_milli` be a positive address integer. Define:

```text
x_i = (q_i - q_max) * 1000 / (LOGIT_SCALE * temperature_milli)
w_i = max(1, round_half_even(exp(x_i) * WEIGHT_SCALE))
```

Reference:

```python
from decimal import Decimal, ROUND_HALF_EVEN, localcontext


WEIGHT_SCALE = 1 << 24
FREQUENCY_TOTAL = 32768


def deterministic_weights(scores: list[int], temperature_milli: int) -> list[int]:
    if not 100 <= temperature_milli <= 2000:
        raise ValueError("temperature outside v1 range")
    maximum = max(scores)
    weights: list[int] = []
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        denominator = Decimal(LOGIT_SCALE * temperature_milli)
        for score in scores:
            exponent = Decimal((score - maximum) * 1000) / denominator
            scaled = exponent.exp() * Decimal(WEIGHT_SCALE)
            weight = int(scaled.to_integral_value(rounding=ROUND_HALF_EVEN))
            weights.append(max(1, weight))
    return weights
```

For long-term cross-language implementations, the Decimal exponential SHOULD
eventually be replaced by a protocol-published integer lookup table generated
once and checked into testdata. Until then, v1 interoperability is explicitly
Python-profile interoperability.

### 18.3 Largest-remainder normalization

Reserve one count for each symbol, distribute the remaining total in
proportion to weights, then distribute leftover counts by largest remainder.
Ties follow candidate order.

```python
def frequency_counts(weights: list[int], total: int = FREQUENCY_TOTAL) -> list[int]:
    count = len(weights)
    if count < 2 or count >= total:
        raise ValueError("invalid candidate count")
    if any(weight <= 0 for weight in weights):
        raise ValueError("weights must be positive")

    available = total - count
    weight_sum = sum(weights)
    counts: list[int] = []
    remainders: list[int] = []
    for weight in weights:
        numerator = weight * available
        quotient, remainder = divmod(numerator, weight_sum)
        counts.append(1 + quotient)
        remainders.append(remainder)

    missing = total - sum(counts)
    order = sorted(range(count), key=lambda i: (-remainders[i], i))
    for index in order[:missing]:
        counts[index] += 1

    assert all(value > 0 for value in counts)
    assert sum(counts) == total
    return counts


def cumulative_counts(counts: list[int]) -> list[int]:
    cumulative = [0]
    for count in counts:
        cumulative.append(cumulative[-1] + count)
    if cumulative[-1] != FREQUENCY_TOTAL:
        raise ValueError("frequency total mismatch")
    return cumulative
```

### 18.4 Low-entropy bridge rule

An arithmetic table can be valid yet operationally unusable. For example, a
symbol with count 32767 out of 32768 can produce a very long run of selected
symbols without confirming one source bit. A generic token timeout would make
this failure surprising and input-dependent.

V1 therefore has a deterministic bridge rule. Before consuming or recovering
an arithmetic symbol, calculate the final frequency counts. If:

```text
max(counts) > MAX_CODING_SYMBOL_FREQUENCY
```

then the step carries no data. Bob MUST append candidate index zero, Alice MUST
require observed candidate index zero, and neither side updates its arithmetic
coder. The visible prefix and model context advance normally. This token is a
**bridge token**.

At most `MAX_CONSECUTIVE_BRIDGE_TOKENS` may occur before one data symbol. If the
next 33rd context is also over-concentrated, the carrier trial fails. This
prevents a deterministic low-entropy model region from producing unbounded
cover text.

Bridge behavior is part of `cm-arithmetic-v1`. It does not require a marker in
the payload because Alice independently computes the same frequency table from
the visible prefix. The self-test records all counts, including tables that
would trigger bridging.

## 19. Arithmetic coding

### 19.1 Direction of operation

Covermail uses a useful inversion of a normal arithmetic coder:

- Bob treats the framed ciphertext bits as the arithmetic **code value** and
  repeatedly decodes that bitstream into model-symbol indices;
- Alice observes the symbol indices represented by carrier tokens and runs the
  matching arithmetic **encoder**, recovering the original bits.

Because HPKE ciphertext is computationally indistinguishable from random, the
selected symbols approximately follow the normalized model distribution rather
than a uniform selection among top tokens.

### 19.2 Integer range

All range state uses unsigned 32-bit arithmetic:

```python
PRECISION = 32
FULL = 1 << PRECISION
MASK = FULL - 1
HALF = 1 << 31
QUARTER = 1 << 30
THREE_QUARTERS = 3 << 30
```

Initial state:

```text
low  = 0
high = 2^32 - 1
```

Multiplications use unbounded intermediate integers, then normalized range
values are masked to 32 bits as specified. Python naturally provides unbounded
intermediates.

### 19.3 Bit order and virtual suffix

Bytes are read most-significant bit first. After all real frame bits, the
source supplies an infinite alternating suffix:

```text
1, 0, 1, 0, 1, 0, ...
```

This suffix initializes and advances the 32-bit arithmetic code after the
payload boundary without adding bytes to the wire frame. The receiver validates
any confirmed bits beyond the frame against the same suffix.

```python
class FramedBitSource:
    def __init__(self, data: bytes):
        self.data = data

    @property
    def real_bits(self) -> int:
        return len(self.data) * 8

    def bit(self, offset: int) -> int:
        if offset < self.real_bits:
            byte = self.data[offset // 8]
            return (byte >> (7 - offset % 8)) & 1
        return 1 if (offset - self.real_bits) % 2 == 0 else 0
```

### 19.4 Bits-to-symbols arithmetic decoder

```python
from bisect import bisect_right
from collections.abc import Callable


class ArithmeticSymbolDecoder:
    """Consumes source bits and selects arithmetic symbols."""

    def __init__(self, read_bit: Callable[[], int]):
        self.low = 0
        self.high = MASK
        self.code = 0
        self.read_bit = read_bit
        for _ in range(PRECISION):
            self.code = ((self.code << 1) | read_bit()) & MASK

    def symbol(self, cumulative: list[int]) -> int:
        range_size = self.high - self.low + 1
        scaled = ((self.code - self.low + 1) * FREQUENCY_TOTAL - 1) // range_size
        symbol = bisect_right(cumulative, scaled) - 1
        if symbol < 0 or symbol + 1 >= len(cumulative):
            raise RuntimeError("arithmetic symbol outside table")

        old_low = self.low
        self.high = old_low + range_size * cumulative[symbol + 1] // FREQUENCY_TOTAL - 1
        self.low = old_low + range_size * cumulative[symbol] // FREQUENCY_TOTAL

        while True:
            if self.high < HALF:
                pass
            elif self.low >= HALF:
                self.low -= HALF
                self.high -= HALF
                self.code -= HALF
            elif self.low >= QUARTER and self.high < THREE_QUARTERS:
                self.low -= QUARTER
                self.high -= QUARTER
                self.code -= QUARTER
            else:
                break

            self.low = (self.low << 1) & MASK
            self.high = ((self.high << 1) | 1) & MASK
            self.code = ((self.code << 1) | self.read_bit()) & MASK

        return symbol
```

`bisect_right(cumulative, scaled) - 1` is valid because cumulative boundaries
start at zero and end at `FREQUENCY_TOTAL`; test boundary values exhaustively.

### 19.5 Symbols-to-bits arithmetic encoder

```python
class ArithmeticBitEncoder:
    """Consumes arithmetic symbols and emits confirmed prefix bits."""

    def __init__(self, emit_bit: Callable[[int], None]):
        self.low = 0
        self.high = MASK
        self.pending = 0
        self.emit_bit = emit_bit

    def _output(self, bit: int) -> None:
        self.emit_bit(bit)
        while self.pending:
            self.emit_bit(bit ^ 1)
            self.pending -= 1

    def symbol(self, symbol: int, cumulative: list[int]) -> None:
        if symbol < 0 or symbol + 1 >= len(cumulative):
            raise ValueError("invalid arithmetic symbol")
        range_size = self.high - self.low + 1
        old_low = self.low
        self.high = old_low + range_size * cumulative[symbol + 1] // FREQUENCY_TOTAL - 1
        self.low = old_low + range_size * cumulative[symbol] // FREQUENCY_TOTAL

        while True:
            if self.high < HALF:
                self._output(0)
            elif self.low >= HALF:
                self._output(1)
                self.low -= HALF
                self.high -= HALF
            elif self.low >= QUARTER and self.high < THREE_QUARTERS:
                self.pending += 1
                self.low -= QUARTER
                self.high -= QUARTER
            else:
                break

            self.low = (self.low << 1) & MASK
            self.high = ((self.high << 1) | 1) & MASK
```

The encoder is not explicitly flushed for Covermail data termination. Bob stops
only after a mirrored encoder has already emitted every real frame bit. This is
critical and must not be replaced by a conventional finalization step without
changing the codec version.

### 19.6 Bob's exact termination algorithm

Bob maintains both:

- the arithmetic decoder selecting symbols from payload bits;
- a mirrored arithmetic encoder consuming those symbols and emitting confirmed
  bits.

Every emitted mirror bit MUST equal the bit source at the same offset. Bob
stops selecting data symbols once the mirror has confirmed at least all real
frame bits.

```python
def select_data_symbols(
    stego_frame: bytes,
    next_table: Callable[[list[int]], tuple[list[Candidate], list[int]]],
) -> list[int]:
    source = FramedBitSource(stego_frame)
    read_offset = 0

    def read_bit() -> int:
        nonlocal read_offset
        value = source.bit(read_offset)
        read_offset += 1
        return value

    selected_token_ids: list[int] = []
    confirmed = 0
    desynchronized = False

    def confirm(bit: int) -> None:
        nonlocal confirmed, desynchronized
        if bit != source.bit(confirmed):
            desynchronized = True
        confirmed += 1

    decoder = ArithmeticSymbolDecoder(read_bit)
    mirror = ArithmeticBitEncoder(confirm)

    token_guard = max(1024, len(stego_frame) * 64 + 1024)
    consecutive_bridges = 0
    while confirmed < source.real_bits:
        candidates, cumulative = next_table(selected_token_ids)
        counts = [cumulative[i + 1] - cumulative[i] for i in range(len(candidates))]
        if max(counts) > MAX_CODING_SYMBOL_FREQUENCY:
            consecutive_bridges += 1
            if consecutive_bridges > MAX_CONSECUTIVE_BRIDGE_TOKENS:
                raise RuntimeError("model context remained too low-entropy")
            selected_token_ids.append(candidates[0].token_id)
            continue

        consecutive_bridges = 0
        symbol = decoder.symbol(cumulative)
        mirror.symbol(symbol, cumulative)
        if desynchronized:
            raise RuntimeError("arithmetic mirror desynchronized")
        selected_token_ids.append(candidates[symbol].token_id)
        if len(selected_token_ids) > token_guard:
            raise RuntimeError("arithmetic coder failed to make progress")

    return selected_token_ids
```

The real implementation's `next_table` takes prompt context and visible token
IDs separately, applies copy-safe filtering, returns the exact final candidates,
and may use a KV cache. The simplified callback above documents termination.

### 19.7 Alice's recovery algorithm

Alice tokenizes the exact carrier body to observed token IDs. For each observed
token, she recomputes the final candidate list for that visible prefix. Before
the data frame is complete, she first applies the low-entropy bridge rule. At a
bridge step the observed token must be candidate zero and no arithmetic state
is updated. At a data step the token must appear in the list and its index is
fed to `ArithmeticBitEncoder`.

Emitted bits are accumulated MSB-first into bytes. After each newly completed
byte:

1. parse the canonical outer length varint if possible;
2. reject an invalid or excessive declaration;
3. calculate `target_bits = (header_bytes + declared_length) * 8`;
4. once emitted-bit count reaches `target_bits`, record the current token as
   the final data token;
5. validate emitted bits beyond `target_bits` against `1,0,1,0,...`.

Any remaining carrier tokens are finish tokens and must each be the current
greedy candidate at index zero.

```python
class BitCollector:
    def __init__(self):
        self.data = bytearray()
        self.count = 0

    def append(self, bit: int) -> None:
        if self.count % 8 == 0:
            self.data.append(0)
        if bit:
            self.data[self.count // 8] |= 1 << (7 - self.count % 8)
        self.count += 1

    def bit(self, offset: int) -> int:
        return (self.data[offset // 8] >> (7 - offset % 8)) & 1

    def complete_bytes(self) -> bytes:
        return bytes(self.data[: self.count // 8])
```

### 19.8 Finishing tokens

After all data bits are confirmed, Bob detokenizes the selected data tokens.
If the trimmed text already ends in `.`, `!`, or `?`, no finish token is added.
Otherwise Bob repeatedly chooses candidate index zero using the normal final
candidate function until:

- the detokenized text ends in `.`, `!`, or `?`; or
- `finish_tokens` have been appended.

If no sentence ending is reached within the limit, that carrier trial fails.

Alice accepts at most the configured number of trailing finish tokens. Each
must equal candidate index zero for its exact context. The final visible text
must satisfy the structural carrier checks.

### 19.9 Round-trip tokenizer validation

Before Bob returns a carrier:

```text
text = detokenize(generated_token_ids)
tokenize(text) MUST equal generated_token_ids exactly
```

The text must also contain one paragraph, no leading/trailing whitespace, and
no forbidden controls. Failure rejects the carrier trial.

## 20. Carrier trials and quality selection

### 20.1 Independent trials

Each trial MUST call HPKE encryption again, producing fresh encapsulated-key and
ciphertext bytes. Those fresh bits naturally produce a different carrier. Do
not reuse an HPKE ciphertext with arbitrary trial salts.

The sender pipeline is:

```python
options = []
for trial in range(carrier_trials):
    inner = pack_inner(secret_text)       # fresh random message ID
    hpke_blob = encrypt_inner(address, inner)  # fresh HPKE ephemeral key
    payload = outer_header(address) + hpke_blob
    frame = encode_uvarint(len(payload)) + payload
    carrier = encode_with_model(address, subject, frame)
    validate_round_trip(carrier)
    options.append((carrier, score_carrier(carrier)))
selected = choose_carrier(options)
```

The initial UI SHOULD default to two trials and allow one to four. A malicious
address MUST NOT force an excessive trial count; trial count is a local sender
preference, not an address field.

### 20.2 Metrics

Collect at minimum:

- data token count;
- bridge token count and maximum consecutive bridge run;
- finish token count;
- Unicode character count;
- mean adjusted-score regret between candidate zero and selected candidate;
- worst adjusted-score regret;
- structural-style pass/fail;
- optional local semantic-judge score.

Selection SHOULD first reject structurally invalid carriers, then select the
shortest carrier within a configured naturalness slack of the best naturalness
score. The exact selection policy affects detectability but not decoding,
because the selected carrier contains its own independently encrypted payload.

### 20.3 No false guarantees

Carrier selection is a heuristic. The application MUST NOT label a carrier
"undetectable". Suitable UI wording is "passes local plausibility checks".

## 21. Complete encode pipeline

Normative order:

1. parse and validate Alice's public address;
2. verify all local model artifacts;
3. run the address compatibility self-test;
4. canonicalize the visible subject;
5. validate secret UTF-8 size;
6. estimate carrier cost and require user confirmation above warning budget;
7. for each local carrier trial:
   1. pack a fresh inner frame;
   2. encrypt it with HPKE Base and address-bound `info`;
   3. build outer payload;
   4. prepend canonical outer-length varint;
   5. build deterministic prompt from address and subject;
   6. select data tokens using inverse arithmetic coding;
   7. add greedy finish tokens;
   8. detokenize and require exact retokenization;
   9. run structural and optional semantic checks;
8. select the best acceptable carrier;
9. return subject, carrier body, metrics, address ID, and a local-only message
   receipt;
10. do not transmit anything automatically in v1.

The local receipt MAY store the secret plaintext only if the user explicitly
enables local history. Default history should retain metadata and carrier, not
secret plaintext.

High-level reference:

```python
def encode_covermail(address, subject, secret, model, *, trials=2):
    validated = validate_address(address)
    model.verify_manifest(validated["model"])
    verify_self_test(validated, model)
    canonical = canonical_subject(subject)

    options = []
    for _ in range(trials):
        inner = pack_inner(secret)
        hpke_blob = encrypt_inner(validated, inner)
        payload = outer_header(validated) + hpke_blob
        frame = encode_uvarint(len(payload)) + payload
        carrier, metrics = generative_encode(validated, canonical, frame, model)
        validate_carrier_round_trip(validated, canonical, carrier, model)
        options.append((carrier, metrics))

    return choose_carrier(options)
```

## 22. Complete decode pipeline

Normative order:

1. select a local private identity/address;
2. parse and validate its public address;
3. verify local model artifacts;
4. run compatibility self-test;
5. canonicalize the received visible subject;
6. validate the pasted carrier structure and hard limits;
7. tokenize the carrier exactly;
8. rebuild the prompt;
9. recover the framed bytes with arithmetic symbol encoding;
10. validate the frame length, virtual suffix, finish tokens, protocol version,
    and address ID;
11. unlock Alice's private key;
12. HPKE-decrypt `hpke_blob` using address-bound `info`;
13. parse and safely decompress the inner frame;
14. optionally check the encrypted message ID against local replay history;
15. display the secret plaintext;
16. wipe references to unlocked key and plaintext when leaving the view as far
    as practical in Python and browser code.

High-level reference:

```python
def decode_covermail(address, private_key, subject, carrier, model):
    validated = validate_address(address)
    model.verify_manifest(validated["model"])
    verify_self_test(validated, model)
    canonical = canonical_subject(subject)

    frame = generative_decode(validated, canonical, carrier, model)
    payload_len, header_len = decode_uvarint(frame, 0)
    payload = frame[header_len:]
    if len(payload) != payload_len:
        raise DecodeError("carrier frame length mismatch")
    if payload[:17] != outer_header(validated):
        raise DecodeError("carrier is for another address or version")

    inner = decrypt_inner(validated, private_key, payload[17:])
    message_id, plaintext = unpack_inner(inner)
    return message_id, plaintext
```

No plaintext from failed HPKE authentication may be exposed.

## 23. Error taxonomy

Internal typed errors SHOULD include:

- `AddressParseError`
- `AddressValidationError`
- `AddressFingerprintMismatch`
- `ModelArtifactMissing`
- `ModelArtifactHashMismatch`
- `ModelCompatibilityError`
- `SubjectValidationError`
- `SecretTooLarge`
- `CarrierBudgetExceeded`
- `CarrierGenerationError`
- `CarrierStructureError`
- `CarrierTokenizationError`
- `CarrierArithmeticError`
- `WrongAddressError`
- `PrivateKeyLockedError`
- `DecryptionError`
- `InnerFrameError`
- `ReplayWarning`

User-facing decryption failures should be intentionally less specific after an
untrusted carrier is supplied. Logs MUST NOT include secrets, private key bytes,
passphrases, full recovered HPKE plaintext, or complete hidden payload bytes.

Debug logging of token IDs and logits MUST be opt-in and clearly warn that it
may expose protocol traces. Generated carrier text is public by design but may
still be personal and should not be logged by default.

## 24. FastAPI local application

### 24.1 Deployment model

The application is a local process:

```text
browser on loopback
       |
       v
FastAPI / Uvicorn bound only to 127.0.0.1 or ::1
       |
       +-- address and identity service
       +-- HPKE protocol service
       +-- model manager
       +-- generative codec
       +-- static local web UI
```

There is no Covermail cloud service. The reference application MUST refuse a
non-loopback bind unless the user starts an explicit expert/debug mode with a
warning.

### 24.2 Local web security

Even loopback services can be targeted by malicious web pages. The server MUST:

- bind loopback only;
- validate `Host` against the actual loopback host and chosen port;
- set no permissive CORS headers;
- reject cross-origin `Origin` and `Referer` values;
- create a fresh random session token at startup;
- require that token in a custom header for every mutating or secret-bearing
  API request;
- set a strict Content Security Policy;
- serve every script, stylesheet, font, and image locally without a CDN or
  runtime third-party origin;
- set `Cache-Control: no-store` on secret-bearing responses;
- avoid cookies for authentication;
- reject form-encoded requests for JSON endpoints;
- cap request body size before parsing;
- never expose filesystem paths directly from address input;
- terminate model jobs when the application exits where the backend permits.

The CLI SHOULD print the local URL containing a one-time bootstrap token or
open the browser itself. After the first page load, the token should be kept in
memory, not localStorage.

### 24.3 API versioning

All endpoints are under `/api/v1`. Suggested API:

```text
GET  /api/v1/health
GET  /api/v1/identities
POST /api/v1/identities
POST /api/v1/identities/{id}/unlock-check
POST /api/v1/addresses/inspect
POST /api/v1/models/prepare
GET  /api/v1/models/{address_id}/status
POST /api/v1/messages/estimate
POST /api/v1/messages/encode
POST /api/v1/messages/decode
GET  /api/v1/jobs/{job_id}
GET  /api/v1/jobs/{job_id}/events
DELETE /api/v1/jobs/{job_id}
```

Generation is long-running. `encode`, `decode`, and model preparation SHOULD
create bounded in-memory jobs and expose progress via server-sent events.
Only one heavy model operation per loaded device should run by default.

### 24.4 Pydantic request examples

```python
from pydantic import BaseModel, Field, SecretStr


class EstimateRequest(BaseModel):
    address: dict
    subject: str = Field(min_length=1, max_length=256)
    secret: str = Field(max_length=65535)


class EncodeRequest(EstimateRequest):
    carrier_trials: int = Field(default=2, ge=1, le=4)


class DecodeRequest(BaseModel):
    identity_id: str
    passphrase: SecretStr = Field(min_length=1, max_length=1024)
    subject: str = Field(min_length=1, max_length=256)
    carrier: str = Field(min_length=1, max_length=200000)
```

Passphrases MUST use Pydantic secret types or equivalent redaction and MUST
never appear in validation-error representations or access logs. Uvicorn access
logging SHOULD be disabled or filtered for secret-bearing routes.

### 24.5 Job states

```text
queued -> loading_model -> self_test -> framing -> generating_trials
       -> validating -> complete
       -> failed
       -> cancelled
```

Progress events MUST contain only safe metadata such as stage, trial index,
tokens generated, estimated remaining work, and public carrier preview if the
user explicitly enabled live preview. They MUST NOT stream secret plaintext or
private key material.

## 25. User experience specification

### 25.1 Home screen

Three primary actions:

1. **Create my Covermail Address**
2. **Write to a Covermail Address**
3. **Read a Covermail message**

An advanced link shows model management and protocol diagnostics.

### 25.2 Create address flow

1. Explain that this creates a recipient key and may download a large model.
2. Ask for display label; state clearly it is public and not authenticated by
   itself.
3. Choose one supported model/runtime profile from a curated list.
4. Choose language and cover profile fields.
5. Choose and confirm a private-key passphrase.
6. Download/verify model artifacts.
7. Generate X25519 key pair.
8. Run model self-test and create immutable address.
9. Save encrypted private identity.
10. Offer public JSON download, QR representation, and copyable fingerprint.
11. Require a checkbox acknowledging that fingerprint verification prevents
    address substitution.

The private export and public export MUST be visually distinct. The application
must never suggest sharing `private-key.pem` or a private identity archive.

### 25.3 Write flow

1. Import or select Alice's public address.
2. Show recipient label, full fingerprint, model download status, language, and
   cover profile.
3. Require fingerprint-confirmation state. It may be remembered locally.
4. Prepare and self-test the exact model.
5. Ask for visible outer subject.
6. Ask for secret email.
7. Continuously show:
   - UTF-8 plaintext bytes;
   - estimated compressed bytes;
   - fixed HPKE overhead;
   - estimated carrier tokens and characters;
   - warning if outside recommended budget.
8. Generate one or more trials with progress.
9. Show chosen carrier, metrics, and "passes local plausibility checks" status.
10. Provide separate copy buttons for subject and body.
11. Display transport instructions and a local receipt/save option.

The UI MUST NOT automatically send email in v1.

### 25.4 Read flow

1. Select private identity/address.
2. Ensure model artifacts and self-test pass.
3. Paste visible subject.
4. Paste exact one-paragraph body.
5. Ask for private-key passphrase as late as practical, preferably only after
   successful generative envelope extraction and address-ID validation.
6. Decode with progress.
7. On success display secret email and optional replay warning.
8. Provide copy and clear buttons.
9. Clear plaintext when navigating away or after a user-configurable timeout.

### 25.5 Error wording

Examples:

- compatibility: "This device does not reproduce the model profile required by
  Alice's address. Do not send; Alice may be unable to decode it."
- transport edit: "The pasted text cannot be reproduced token-for-token. Copy
  only the exact original carrier paragraph."
- generic decrypt: "This is not an authentic message for the selected Covermail
  Address, or the text/configuration has changed."
- size: "The secret is likely to produce an unusually long outer email. Shorten
  it or continue in expert mode."

## 26. Resource and denial-of-service limits

Untrusted public addresses and carriers can request expensive work. Enforce:

- public-address byte cap before JSON parsing;
- strict schema and integer ranges;
- supported-model allowlist for normal mode;
- explicit confirmation before model downloads;
- artifact total-size display and configured maximum;
- no `trust_remote_code`;
- candidate-pool hard cap;
- carrier character and token caps;
- arithmetic no-progress token guard;
- varint and frame-size caps before allocation;
- bounded DEFLATE output;
- bounded concurrent jobs and queue length;
- job timeouts and cancellation where backend supports them;
- no arbitrary URL fetch from imported address fields;
- no arbitrary file reads from artifact paths.

The API MUST not reveal whether an arbitrary address ID exists through remote
network behavior because the service is loopback-only; nevertheless use generic
errors for private identity lookup failures.

## 27. Capacity estimation

The UI estimate is advisory. It should calculate exact pre-LLM sizes:

```text
inner bytes = 2 + 16 + len(uvarint(original_len)) + chosen body bytes
HPKE bytes  = 32 + inner bytes + 16
outer bytes = 1 + 16 + HPKE bytes
frame bytes = len(uvarint(outer bytes)) + outer bytes
hidden bits = frame bytes * 8
```

Estimated model tokens require an empirical entropy-per-token profile measured
for the selected address model and cover profile:

```text
estimated_tokens = ceil(hidden_bits / measured_confirmed_bits_per_token)
```

The application SHOULD maintain benchmark metadata per supported model profile,
including median and p90 confirmed bits/token, visible characters/token, and
generation speed. It MUST label the estimate as such.

The initial product warning threshold is 512 UTF-8 plaintext bytes, not a claim
that 512 bytes always produce a plausible carrier. Actual warning should use
estimated visible length when benchmark data exists.

## 28. Proposed Python project layout

The new repository should become:

```text
covermail/
  pyproject.toml
  uv.lock
  README.md
  LICENSE
  SECURITY.md
  CONTRIBUTING.md
  docs/
    protocol.md
    threat-model.md
    model-profiles.md
    interoperability.md
  src/covermail/
    __init__.py
    cli.py
    app.py
    config.py
    errors.py
    address/
      canonical.py
      fingerprint.py
      schema.py
      service.py
    crypto/
      hpke.py
      identity.py
      private_store.py
    protocol/
      inner_frame.py
      outer_frame.py
      varint.py
    codec/
      arithmetic.py
      bits.py
      candidates.py
      frequencies.py
      generative.py
      self_test.py
    models/
      base.py
      manifest.py
      manager.py
      mlx_adapter.py
      transformers_adapter.py
    cover/
      prompt.py
      profile.py
      transport.py
      quality.py
    api/
      dependencies.py
      schemas.py
      routes_addresses.py
      routes_identities.py
      routes_models.py
      routes_messages.py
      routes_jobs.py
      security.py
    jobs/
      manager.py
      events.py
    web/
      index.html
      app.js
      styles.css
  tests/
    unit/
    integration/
    interoperability/
    security/
    fixtures/
  scripts/
    build_model_manifest.py
    generate_self_test.py
    benchmark_profile.py
  .github/workflows/
    test.yml
    dependency-review.yml
```

### 28.1 Suggested `pyproject.toml`

Versions must ultimately be locked in `uv.lock`; this is a starting point:

```toml
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = "covermail"
version = "0.1.0"
description = "Stateless public-key generative cover email experiment"
readme = "README.md"
requires-python = ">=3.12,<3.14"
license = { text = "MIT" }
dependencies = [
  "cryptography==49.0.0",
  "fastapi>=0.116,<1",
  "pydantic>=2.11,<3",
  "uvicorn[standard]>=0.35,<1",
  "numpy>=2.2,<3",
]

[project.optional-dependencies]
mlx = [
  "mlx>=0.28,<1",
  "mlx-lm>=0.26,<1",
]
transformers = [
  "torch>=2.7,<3",
  "transformers>=4.53,<5",
  "huggingface-hub>=0.33,<1",
]
dev = [
  "httpx>=0.28,<1",
  "hypothesis>=6.135,<7",
  "mypy>=1.16,<2",
  "pytest>=8.4,<9",
  "pytest-asyncio>=1,<2",
  "pytest-cov>=6.2,<7",
  "ruff>=0.12,<1",
]

[project.scripts]
covermail = "covermail.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
```

These package bounds are not normative protocol values. The first implementation
session MUST resolve actual compatible versions, create `uv.lock`, and record
the qualified runtime versions in model profiles.

## 29. Testing requirements

### 29.1 Unit tests

At minimum:

- canonical JSON is invariant to input whitespace and object order;
- duplicate keys are rejected;
- address digest and fingerprint fixtures;
- base64url strict parsing;
- all uvarint boundary values and non-canonical rejections;
- inner raw and compressed round trips;
- decompression bombs, trailing data, truncation, and invalid UTF-8;
- HPKE round trip and wrong key/info/tamper failure;
- outer frame parsing and wrong address ID;
- logit quantization boundary/tie cases;
- largest-remainder frequency sums and positive counts;
- arithmetic interval boundaries;
- randomized bits -> symbols -> bits recovery;
- deterministic low-entropy bridge insertion and rejection after 32 bridges;
- exact termination at every bit offset modulo eight;
- finish-token validation;
- copy-safe filtering;
- subject canonicalization;
- self-test transcript format and hash.

### 29.2 Property tests

Use Hypothesis for:

- arbitrary byte frames up to practical test limits;
- randomized positive frequency tables summing to 32768;
- arithmetic round trips across skewed distributions;
- random Unicode secret messages;
- malformed varints and inner frames;
- bounded decompression behavior;
- JSON schema mutation;
- carrier truncation and single-token substitution with a fake deterministic
  model.

### 29.3 RFC and library vectors

HPKE tests MUST include relevant RFC 9180 vectors where exposed by the selected
library or independently loaded as fixtures. Tests should prove the wrapper uses
the intended X25519/HKDF-SHA256/AES-128-GCM suite and address-bound `info`.

### 29.4 Fake model

Implement a fast deterministic fake model for codec tests. It should have:

- a reversible byte or character tokenizer;
- configurable candidate logits;
- special-token simulation;
- merge-prone token cases for copy-safe tests;
- deterministic prompt dependence;
- enough symbols for skewed arithmetic distributions.

Core CI MUST not download multi-gigabyte models.

### 29.5 Real-model interoperability fixtures

For every supported profile, store metadata and small fixtures:

- complete public test address with non-secret private fixture key;
- subject;
- secret plaintext;
- expected carrier body;
- expected recovered frame and HPKE plaintext in test-only fixtures;
- model artifact hashes;
- runtime and hardware information;
- self-test expected hash.

Run generation on at least two clean installations. Alice must decode Bob's
stored carrier and Bob must decode Alice's independently generated carrier.

An address profile MUST NOT be called supported until cross-installation tests
pass. Cross-hardware support requires tests on every claimed hardware/backend
class.

### 29.6 API and local-security tests

- server binds only loopback by default;
- invalid Host and Origin are rejected;
- no wildcard CORS;
- missing/wrong session token rejected;
- request-size caps occur before JSON/model work;
- passphrases redacted from validation errors and logs;
- secret responses use `Cache-Control: no-store`;
- CSP blocks remote scripts and connections;
- concurrent-job limits;
- cancellation and cleanup;
- malicious artifact paths rejected.

### 29.7 Manual email-client matrix

Test copy/send/receive through at least:

- Gmail web;
- Apple Mail;
- Outlook web or desktop;
- Proton Mail;
- one plain-text CLI client if available.

Record whether each client changes:

- Unicode normalization;
- apostrophes and quotes;
- consecutive spaces;
- hard wrapping;
- terminal newline;
- HTML/plain-text MIME representation;
- automatic signatures;
- copied visible body text.

V1 support claims must be phrased according to observed behavior.

## 30. Implementation stages

The next Codex session should implement in this order.

### Stage 0: repository conversion

- Open `/Users/liliand/conversation-steganography/covermail` directly as the
  workspace folder, or move it to `/Users/liliand/covermail` before coding.
- Preserve this document.
- Remove obsolete Go module files only after confirming no useful user work is
  lost.
- Initialize Python `src/` layout and `pyproject.toml`.
- Create first commit containing only specification/scaffold.
- Configure `lilian-miakito/covermail` after GitHub authentication is repaired.

### Stage 1: protocol without LLM

- canonical address schema and fingerprint;
- X25519 identity generation and encrypted private storage;
- inner frame and bounded compression;
- HPKE wrapper through `cryptography`;
- outer frame;
- CLI test: Alice creates address, Bob encrypts bytes, Alice decrypts bytes;
- exhaustive unit/property tests.

Exit criterion: two processes can exchange independent binary Covermail
payloads using only public address/private identity files.

### Stage 2: arithmetic codec with fake model

- bit source and collector;
- deterministic frequency builder;
- arithmetic decoder/encoder;
- exact framing and finish behavior;
- fake language model;
- randomized property tests;
- corruption/truncation tests.

Exit criterion: arbitrary practical payload bytes round-trip through fake
carrier strings with deterministic fixtures.

### Stage 3: first real model profile

- choose one backend and one exact model, preferably the already available MLX
  Llama profile for initial local work;
- artifact manifest builder;
- model adapter;
- prompt renderer;
- candidate and copy-safe filters;
- address self-test;
- real encode/decode fixture;
- capacity and performance benchmark.

Exit criterion: two clean compatible installations exchange a carrier.

### Stage 4: service and web UI

- FastAPI local service security shell;
- identity/address screens;
- write/read screens;
- model progress and generation jobs;
- budget estimator;
- copy workflows;
- no automatic email integration.

Exit criterion: a non-developer can complete Alice create, Bob write, Alice read
using files and copy/paste.

### Stage 5: hardening

- dependency pinning and update process;
- CI, coverage, lint, type checking;
- fuzz/property expansion;
- email-client matrix;
- cross-machine model qualification;
- threat-model and security documentation;
- release packaging and signed checksums;
- independent cryptographic and protocol review before real-world security
  claims.

## 31. Definition of done for the demonstrator

The demonstrator is complete only when:

- Alice can generate and export a public address and encrypted private identity;
- Bob can import and verify the address fingerprint;
- incompatible model stacks fail before generation;
- Bob can encrypt a short UTF-8 email and generate a carrier;
- the carrier retokenizes exactly;
- Alice can recover it in a separate clean process;
- wrong subject, address, key, edited carrier, truncation, and token substitution
  all fail safely;
- no server/network access is needed after model preparation;
- the local API passes Host/Origin/session-token tests;
- secrets and passphrases are absent from logs;
- unit and property tests pass in CI without a real model;
- at least one opt-in real-model interoperability test passes;
- README states all major limitations without claiming undetectability.

## 32. Open design decisions

These are intentionally not silently fixed by the first implementer:

1. **Initial supported model:** reuse the local MLX Llama 3.2 3B profile for
   speed, or qualify a smaller model with easier distribution.
2. **Model portability:** remain MLX/macOS-first or invest early in a deterministic
   llama.cpp/GGUF profile.
3. **Private-key protection:** encrypted PKCS#8 only or optional OS keychain.
4. **Carrier paragraph style:** one paragraph only in v1 is recommended; line
   breaks would require transport qualification.
5. **Semantic judge:** disabled by default until its determinism and cost are
   characterized.
6. **Padding:** optional plaintext-length buckets improve length privacy but
   materially lengthen carriers. Do not add before capacity measurement.
7. **Post-quantum suite:** cryptography exposes hybrid/PQ KEMs on limited
   backends, but their much larger encapsulations are hostile to steganographic
   capacity. Keep out of v1.
8. **Replay cache:** optional local message-ID cache; it must not become required
   protocol state.
9. **Raw `.eml` import:** valuable after manual copy/paste works across clients.
10. **Repository location:** a sibling `/Users/liliand/covermail` is cleaner than
    the current nested Git repository, but the nested path can be opened directly
    as a standalone Codex workspace immediately.

## 33. Security-review checklist

Before a release, reviewers must answer:

- Is every public-address field either validated or ignored safely?
- Can any address trigger code execution, arbitrary URL fetch, or path traversal?
- Is HPKE provided only by qualified library code?
- Is the exact address digest bound in HPKE `info`?
- Is a fresh HPKE ephemeral key produced for every trial?
- Are private keys encrypted at rest with strict filesystem permissions?
- Can passphrases or plaintext appear in logs, tracebacks, analytics, browser
  storage, caches, or crash reports?
- Does every parser enforce a limit before allocating?
- Is DEFLATE output bounded and exact?
- Are model weights and tokenizer files content-hashed?
- Is remote model code disabled?
- Does the self-test cover prompt, candidates, and frequencies?
- Are candidate ordering and every tie-breaker explicit?
- Are frequency calculations independent of ordinary binary float `exp`?
- Are arithmetic boundary and termination cases property-tested?
- Does the sender validate detokenize/tokenize equality?
- Does the receiver validate finishing tokens and virtual suffix bits?
- Is carrier modification always rejected by framing or HPKE authentication?
- Does the web server enforce loopback, Host, Origin, CSP, and session token?
- Are product claims consistent with the threat model?
- Has another person reviewed the protocol and dependency supply chain?

## 34. Handoff prompt for the next Codex session

The following can be pasted into a new session opened on the `covermail` folder:

> Read `docs/protocol.md` completely before acting. This is a clean MIT Python
> implementation; do not copy GPL code from the parent
> `conversation-steganography` repository. Implement only Stage 0 and Stage 1
> first: convert the scaffold to Python 3.12 with `uv`, create the canonical
> address schema/fingerprint, encrypted X25519 identity storage, bounded inner
> frame/compression, HPKE Base through `cryptography` 49, outer framing, CLI
> round trip, and exhaustive tests. Do not implement the LLM, arithmetic codec,
> or web UI yet. Preserve the protocol formats exactly, flag any contradiction
> before changing the specification, run tests, and stop with a clear handoff.

## 35. References

- RFC 9180, Hybrid Public Key Encryption:
  <https://www.rfc-editor.org/rfc/rfc9180.html>
- pyca/cryptography HPKE 49.0.0:
  <https://cryptography.io/en/49.0.0/hazmat/primitives/hpke/>
- pyca/cryptography X25519:
  <https://cryptography.io/en/stable/hazmat/primitives/asymmetric/x25519/>
- RFC 4648, Base-N Encodings:
  <https://www.rfc-editor.org/rfc/rfc4648.html>
- RFC 8259, JSON:
  <https://www.rfc-editor.org/rfc/rfc8259.html>
- RFC 8785, JSON Canonicalization Scheme, informative comparison:
  <https://www.rfc-editor.org/rfc/rfc8785.html>
- FastAPI security documentation:
  <https://fastapi.tiangolo.com/tutorial/security/>

## 36. Final caution

This specification is a serious implementation plan, not a completed security
proof. The two most uncertain components are statistical cover plausibility and
cross-device deterministic model inference. HPKE can protect plaintext even if
the carrier is recognized, but it cannot make incoherent model output ordinary,
repair modified carrier text, authenticate an unverified public address, or
protect a compromised endpoint.

The correct development posture is therefore:

1. treat HPKE and key distribution as the confidentiality system;
2. treat the generative codec as an experimental camouflage transport;
3. fail closed on every incompatibility;
4. measure carrier capacity and detectability rather than asserting them;
5. add features only after the preceding stage has interoperable fixtures.

## 37. Prototype amendment: `cm-arithmetic-v2`

This section is the normative prototype direction selected after the first real
v1 carrier. For an address whose codec ID is `cm-arithmetic-v2`, this section
supersedes the conflicting v1 prompt, framing, and visible-prefix rules above.
V1 remains readable regression material and is not the forward real-model
profile.

### 37.1 Visible primer

Bob MUST choose one exact visible first sentence before encryption. It MUST:

- contain 1..512 UTF-8 bytes;
- have no leading/trailing whitespace, CR, LF, tab, NUL, model control-token
  substring, or forbidden Unicode control/surrogate/private/unassigned point;
- contain exactly one character from `.!?`, at its final character;
- round-trip through the qualified tokenizer exactly.

The carrier is `primer || coded continuation || deterministic finish`. Alice
extracts through the first terminal punctuation, initializes the visible token
prefix with the primer, and starts arithmetic extraction after those tokens.

### 37.2 Context-bound HPKE and uniformized stream

The v2 visible-context digest is SHA-256 over:

```text
"covermail/visible-context/v2\0"
|| uint16_be(len(subject_utf8)) || subject_utf8
|| uint16_be(len(primer_utf8))  || primer_utf8
```

The HPKE `info` is:

```text
"covermail/hpke/v2\0" || address_digest || outer_header || context_digest
```

Split the HPKE output into its 32-byte encapsulated key `enc` and authenticated
ciphertext. Construct:

```text
payload = outer_header || hpke_ciphertext
tail = uvarint(len(payload)) || payload
mask = HKDF-SHA256(
    ikm=enc,
    salt=address_digest,
    info="covermail/stego-mask/v2\0" || context_digest,
    length=len(tail),
)
v2_stream = enc || (tail XOR mask)
```

The mask is public uniformization, not additional confidentiality. Alice first
recovers the fixed 32-byte `enc`, derives the mask, unmasks the length varint,
then knows the exact arithmetic termination target.

### 37.3 Prompt and candidates

Prompt ID `cm-email-continue-primer-v2` asks the qualified model to continue the
exact first sentence on the visible subject for as long as needed. It has no
normative sentence-count limit. The secret is never included.

Candidate construction remains the deterministic raw top-512 pool, v1 visible
and full-prefix copy-safe filters, final top 64, temperature 1, and integer
frequency normalization. V2 requires `length_bias_milli=0`: selected candidate
probability ratios come directly from quantized LLM logits. No top-p, sampling,
Viterbi, beam search, or best-of-N selection is used.

The existing bridge rule remains: if one frequency exceeds 24576/32768, emit
the top candidate without payload bits. After all real bits are confirmed, emit
deterministic top-1 finish tokens until the carrier ends in `.`, `!`, or `?`.

### 37.4 Capacity metric

V2 does not impose a fixed visible length or sentence count. Implementations
MUST report:

```text
K_all = visible Unicode code points / v2 stream bytes
```

`visible` includes primer, bridge, data, and finish tokens. Implementations MAY
also report UTF-8 carrier bytes per stream byte and bits per data/all token.
