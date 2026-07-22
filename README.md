# Covermail

Covermail hides an already encrypted UTF-8 message in the token choices of a
local language model. The LLM is a steganographic transport, not the cipher.

The repository is work in progress and exposes one protocol only:

- A: 64 ordinary generated tokens guided by a sender-only writing brief;
- B: a fixed 53-byte encrypted metadata capsule containing the length of C;
- C: the independently encrypted message capsule;
- D: an optional local finish which the decoder ignores;
- one continuous 32-bit inverse-arithmetic stream for `B || C`;
- context-bound HPKE with X25519, HKDF-SHA256 and AES-128-GCM;
- deterministic candidate tables from exact local Qwen logits, with no bridge,
  top-p, beam search, fixed bits-per-token rule or compatibility shim.

There is no email-subject field. LF line breaks and natural paragraphs are
ordinary carrier text; CRLF and CR inputs are canonicalized to LF.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run mypy src tests
```

Install the local MLX extra on a qualified Apple Silicon host:

```bash
uv sync --extra dev --extra mlx
```

The active local profile is `mlx-community/Qwen3.5-4B-4bit` at the immutable
revision recorded in
`tests/fixtures/mlx_qwen35_4b_4bit/address.json`.

## Local application

Start the loopback application with the prepared model:

```bash
MODEL_ROOT=.covermail/models/mlx-community--Qwen3.5-4B-4bit/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c
uv run covermail app --model-root "$MODEL_ROOT"
```

Open the ordinary loopback URL printed by the command. The development
application uses no session token, cookie or browser storage.

The UI can create an identity, export/import public addresses, confirm a
recipient fingerprint, estimate a carrier, stream generation token by token,
and recover a hidden message. The write form takes a free writing brief and a
secret; the read form takes only an identity, passphrase and carrier.

The development service binds to `127.0.0.1`, caps JSON bodies before parsing,
disables Uvicorn access logs, serves no remote assets and uses no browser
session mechanism.

## End-to-end commands

```bash
MODEL_ROOT=.covermail/models/mlx-community--Qwen3.5-4B-4bit/0e7ffd5c629ef7719d4cbc04069232580bfa9d9c
BRIEF='Écris à Camille au sujet des tomates du jardin et commence chaleureusement.'

uv run covermail identity-create \
  tests/fixtures/mlx_qwen35_4b_4bit/address.json \
  --identities-dir .covermail/identities \
  --public-address alice.covermail.json

uv run covermail carrier-encode alice.covermail.json \
  --model-root "$MODEL_ROOT" \
  --prompt "$BRIEF" \
  --message secret.txt \
  --output carrier.txt

uv run covermail carrier-decode .covermail/identities/ADDRESS_ID \
  --model-root "$MODEL_ROOT" \
  --carrier carrier.txt \
  --output recovered.txt
```

`carrier-encode` reports `K_all`, characters, UTF-8 bytes, packet bytes and A,
B/C and D token counts. The finish budget can be changed locally with
`--finish-tokens`; it is not part of the address or decoding protocol.

## Cross-installation qualification

Generate a three-case real-model bundle and round-trip every carrier locally:

```bash
uv run covermail model-qualify \
  tests/fixtures/mlx_qwen35_4b_4bit/address.json \
  --model-root "$MODEL_ROOT" \
  --output qualification-host-a.json
```

Copy that JSON to a second compatible installation and verify it:

```bash
uv run covermail model-qualify \
  tests/fixtures/mlx_qwen35_4b_4bit/address.json \
  --model-root "$MODEL_ROOT" \
  --verify-bundle qualification-host-a.json \
  --output verification-host-b.json
```

Reports contain encrypted B/C capsules and visible carriers, never the private
key or hidden plaintext. Lexical flags are observations only: they never reject
an otherwise exact packet and are not a semantic judge or a claim of
undetectability.

The normative implementation draft is [docs/protocol.md](docs/protocol.md).
