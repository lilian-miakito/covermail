# Covermail

Covermail is a public-key generative steganography experiment. It encrypts a message, then encodes the resulting ciphertext in the token choices of a local language model to produce readable cover text.

The language model never sees the plaintext and provides no cryptographic security. Encryption is handled separately with HPKE; the model is only the transport.

## How it works

1. The recipient creates an encrypted local identity and shares a public Covermail address.
2. The sender encrypts a UTF-8 message with the recipient's public key.
3. An arithmetic codec maps the encrypted packet to valid token choices from a local Qwen 3.5 model.
4. The resulting carrier can be copied and sent as ordinary text.
5. The recipient replays the same token distributions, recovers the packet and decrypts the message.

```text
secret
  → HPKE encryption
  → encrypted packet
  → arithmetic coding over Qwen 3.5 token probabilities
  → visible carrier text
```

Both sides must use the exact model, runtime and protocol parameters pinned by the recipient's public address.

## What is included

- the Covermail protocol implementation;
- HPKE recipient identities and portable public addresses;
- deterministic arithmetic encoding over model token distributions;
- a pinned Qwen 3.5 4B profile for MLX on Apple Silicon;
- a command-line interface;
- a local FastAPI application;
- model qualification and cross-installation verification tools;
- property-based, protocol, cryptographic and end-to-end tests.

## Carrier format

A Covermail carrier has four sections:

| Section | Contents |
| --- | --- |
| A | A 64-token visible prefix generated from the sender's writing brief. It carries no message bits. |
| B | A canonical public uvarint containing the byte length of section C. |
| C | One HPKE capsule containing the framed secret. |
| D | An optional visible ending ignored by the decoder. |

Sections B and C form one continuous 32-bit arithmetic stream. Their byte boundary does not need to align with a token boundary.

Line breaks and paragraphs are ordinary carrier text. Inputs using CRLF or CR line endings are canonicalized to LF.

## Cryptography and deterministic generation

Covermail uses HPKE Base mode as specified by RFC 9180:

- DHKEM with X25519 and HKDF-SHA256;
- HKDF-SHA256;
- AES-128-GCM.

The exact public length header, prefix tokens and recipient address are bound to the single encrypted capsule.

Token candidates are derived deterministically from the exact float32 logits of the pinned model revision. The current protocol uses fixed candidate construction and integer frequencies rather than sampling, top-p, beam search or a fixed number of bits per token.

The normative details are documented in [docs/protocol.md](docs/protocol.md).

## Current model profile

The current real-model profile uses:

- `mlx-community/Qwen3.5-4B-4bit`;
- revision `0e7ffd5c629ef7719d4cbc04069232580bfa9d9c`;
- MLX on Apple Silicon;
- exact model artifact hashes, Python version and package versions recorded in the public address.

The deterministic model self-test is pinned in the public profile. A fresh real-model qualification bundle must be generated for the compact single-capsule packet before claiming cross-installation interoperability.

## Public address as interoperability contract

The public address records every input that must remain identical for deterministic
decoding: model ID, immutable revision, SHA-256 and size of each model artifact,
runtime package versions, codec parameters, cover profile and model self-test.
Changing one of those values produces a different address and fails closed before
carrier processing.

The current address is canonical JSON. It contains the recipient's X25519 public
key and the public model profile, never the private key or passphrase.

An abridged public address looks like this:

```json
{
  "format": "covermail-address",
  "version": 1,
  "recipient": {
    "label": "Alice",
    "hpke_public_key": "B6N8vBQgk8i3VdwbEOhstCY3StFqqFPtC9_AsrhtHHw"
  },
  "model": {
    "backend": "mlx-lm",
    "model_id": "mlx-community/Qwen3.5-4B-4bit",
    "revision": "0e7ffd5c629ef7719d4cbc04069232580bfa9d9c"
  }
}
```

The complete address also includes the HPKE suite, artifact hashes, runtime
versions, codec parameters, cover profile and model self-test. Use the complete
exported JSON when sending a message; the shortened example above is not
importable.

## Local application

Install the project and the MLX dependencies:

```bash
uv sync --extra dev --extra mlx
```

Download the immutable model snapshot, then materialize only the artifacts named
by the active profile:

```bash
SNAPSHOT_ROOT=.covermail/snapshots/qwen35-4b
MODEL_ROOT=.covermail/models/mlx-community--Qwen3.5-4B-4bit/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c

uv run hf download mlx-community/Qwen3.5-4B-4bit \
  --revision 0e7ffd5c629ef7719d4cbc04069232580bfa9d9c \
  --local-dir "$SNAPSHOT_ROOT"

uv run covermail model-prepare \
  --source "$SNAPSHOT_ROOT" \
  --destination "$MODEL_ROOT"
```

Start the application with that qualified model tree:

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

For example, Bob can hide this message for Alice:

```text
Meet at noon.
```

The beginning of the visible carrier may read:

```text
Hey Alice,

Just wanted to let you know that the plumber had to reschedule our Saturday appointment. I think it's getting moved to next week, so we might have to find a new date soon.

On the bright side, does Sunday still work for our coffee? I was hoping to catch up properly once we get that fixed. Let me know, just so we can adjust accordingly.
```

This excerpt is shortened for readability and cannot be decoded on its own.
Alice receives the complete carrier, replays the pinned Qwen 3.5 token
distributions and opens the recovered HPKE capsule with her private key.

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
