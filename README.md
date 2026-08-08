# Covermail

Covermail is a public-key generative steganography experiment. It encrypts a message, then encodes the resulting ciphertext in the token choices of a local language model to produce readable cover text.

The language model never sees the plaintext and provides no cryptographic security. Encryption is handled separately with HPKE; the model is only the transport.

## How it works

1. The recipient creates an encrypted local identity and shares a public Covermail address.
2. The sender encrypts a UTF-8 message with the recipient's public key.
3. An arithmetic codec maps the encrypted packet to valid token choices from a local Qwen model.
4. The resulting carrier can be copied and sent as ordinary text.
5. The recipient replays the same token distributions, recovers the packet and decrypts the message.

```text
secret
  → HPKE encryption
  → encrypted packet
  → arithmetic coding over Qwen token probabilities
  → visible carrier text
```

Both sides must use the exact model, runtime and protocol parameters pinned by the recipient's public address.

## What is included

- the Covermail protocol implementation;
- HPKE recipient identities and portable public addresses;
- deterministic arithmetic encoding over model token distributions;
- a qualified Qwen profile for MLX on Apple Silicon;
- a command-line interface;
- a local FastAPI application;
- model qualification and cross-installation verification tools;
- property-based, protocol, cryptographic and end-to-end tests.

## Carrier format

A Covermail carrier has four sections:

| Section | Contents |
| --- | --- |
| A | A 64-token visible prefix generated from the sender's writing brief. It carries no message bits. |
| B | A fixed 53-byte encrypted metadata capsule containing the length of section C. |
| C | The encrypted message capsule. |
| D | An optional visible ending ignored by the decoder. |

Sections B and C form one continuous 32-bit arithmetic stream. Their byte boundary does not need to align with a token boundary.

Line breaks and paragraphs are ordinary carrier text. Inputs using CRLF or CR line endings are canonicalized to LF.

## Cryptography and deterministic generation

Covermail uses HPKE Base mode as specified by RFC 9180:

- DHKEM with X25519 and HKDF-SHA256;
- HKDF-SHA256;
- AES-128-GCM.

The metadata and message are encrypted independently. The exact prefix tokens and the recipient's canonical public address are bound to both encrypted capsules.

Token candidates are derived deterministically from the exact float32 logits of the pinned model revision. The current protocol uses fixed candidate construction and integer frequencies rather than sampling, top-p, beam search or a fixed number of bits per token.

The normative details are documented in [docs/protocol.md](docs/protocol.md).

## Current model profile

The current real-model profile uses:

- `mlx-community/Qwen3.5-4B-4bit`;
- revision `0e7ffd5c629ef7719d4cbc04069232580bfa9d9c`;
- MLX on Apple Silicon;
- Python 3.12 or 3.13.

The committed qualification bundle contains three independently generated carriers:

| Measure | Result |
| --- | --- |
| Encrypted packet size | 150–171 bytes |
| Carrier size | 710–777 tokens |
| Visible characters per encrypted byte | 18.42–18.45 |
| Generation speed | 27.3–27.9 tokens/s |
| Exact local recovery | 3/3 carriers |

These figures were measured on the qualification host. Reproduction and bidirectional verification on a second clean installation are still required before claiming cross-installation interoperability.

## Local application

Install the project and the MLX dependencies:

```bash
uv sync --extra dev --extra mlx
```

With the qualified model already prepared locally:

```bash
MODEL_ROOT=.covermail/models/mlx-community--Qwen3.5-4B-4bit/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c

uv run covermail app --model-root "$MODEL_ROOT"
```

Open the loopback URL printed by the command.

The application can:

- create an encrypted recipient identity;
- export and import public addresses;
- display and confirm recipient fingerprints;
- estimate carrier size;
- stream carrier generation token by token;
- recover a hidden message from carrier text.

It binds to `127.0.0.1`, serves no remote assets and uses no browser storage, cookies or session mechanism.

## Command-line round trip

Create a recipient identity:

```bash
uv run covermail identity-create \
  tests/fixtures/mlx_qwen35_4b_4bit/address.json \
  --identities-dir .covermail/identities \
  --public-address alice.covermail.json
```

Encode a message:

```bash
BRIEF='Write a warm email to Camille about the tomatoes from the garden.'

uv run covermail carrier-encode alice.covermail.json \
  --model-root "$MODEL_ROOT" \
  --prompt "$BRIEF" \
  --message secret.txt \
  --output carrier.txt
```

Decode the carrier with the recipient's identity:

```bash
uv run covermail carrier-decode .covermail/identities/ADDRESS_ID \
  --model-root "$MODEL_ROOT" \
  --carrier carrier.txt \
  --output recovered.txt
```

`carrier-encode` reports the encrypted packet size, carrier size, token counts and the `K_all` expansion measure.

## Qualification

Generate a real-model qualification bundle and verify every carrier locally:

```bash
uv run covermail model-qualify \
  tests/fixtures/mlx_qwen35_4b_4bit/address.json \
  --model-root "$MODEL_ROOT" \
  --output qualification-host-a.json
```

Verify the bundle on a second compatible installation:

```bash
uv run covermail model-qualify \
  tests/fixtures/mlx_qwen35_4b_4bit/address.json \
  --model-root "$MODEL_ROOT" \
  --verify-bundle qualification-host-a.json \
  --output verification-host-b.json
```

Qualification reports contain encrypted capsules and visible carriers. They do not contain the private key or hidden plaintext.

## Security boundaries

Covermail provides:

- public-key encryption of the hidden message;
- ciphertext integrity;
- binding to the recipient address and exact carrier prefix;
- strict validation of the model and protocol profile.

Covermail does not provide:

- sender authentication;
- replay protection;
- protection against compromised endpoints;
- protection against public-address substitution;
- transport metadata or approximate message-length hiding;
- recovery after the carrier text has been edited;
- a claim of undetectability or resistance to trained steganalysis.

See [docs/threat-model.md](docs/threat-model.md) for the complete threat model.

## Development

```bash
uv sync --extra dev --extra mlx
uv run pytest
uv run ruff check .
uv run mypy src tests
```

Additional documentation:

- [Protocol](docs/protocol.md)
- [Threat model](docs/threat-model.md)
- [Interoperability](docs/interoperability.md)
- [Model profiles](docs/model-profiles.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

MIT
