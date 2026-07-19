# Covermail

Covermail hides an already encrypted message in the token choices of a local
language model. The LLM is a steganographic channel, not the cryptographic
cipher.

The repository is work in progress and exposes one protocol only:

- codec ID `cm-arithmetic`;
- an exact visible subject and first-sentence primer;
- context-bound HPKE using X25519, HKDF-SHA256, and AES-128-GCM;
- inverse 32-bit arithmetic coding over deterministic LLM probabilities;
- every candidate table updates arithmetic state; no sampling API, top-p,
  beam search, or compatibility shims;
- LF line breaks and natural paragraphs are valid carrier text;
- CRLF and CR inputs are canonicalized to LF before tokenization.

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

The current local model profile is
`mlx-community/Llama-3.2-3B-Instruct-4bit` at the immutable revision recorded
in `tests/fixtures/mlx_llama32_3b_4bit/address.json`.

## End-to-end commands

```bash
MODEL_ROOT=.covermail/models/mlx-community--Llama-3.2-3B-Instruct-4bit/7f0dc925e0d0afb0322d96f9255cfddf2ba5636e
SUBJECT='Des nouvelles du jardin'
PRIMER='Je voulais te raconter calmement ce qui est arrivé au jardin.'

uv run covermail identity-create \
  tests/fixtures/mlx_llama32_3b_4bit/address.json \
  --identities-dir .covermail/identities \
  --public-address alice.covermail.json

uv run covermail encrypt alice.covermail.json \
  --subject "$SUBJECT" --primer "$PRIMER" \
  --message secret.txt --output message.cm

uv run covermail carrier-encode alice.covermail.json \
  --model-root "$MODEL_ROOT" \
  --subject "$SUBJECT" --primer "$PRIMER" \
  --stream message.cm --output carrier.txt

uv run covermail carrier-decode alice.covermail.json \
  --model-root "$MODEL_ROOT" \
  --subject "$SUBJECT" \
  --carrier carrier.txt --output decoded.cm \
  --primer-output decoded-primer.txt

uv run covermail decrypt .covermail/identities/ADDRESS_ID \
  --subject "$SUBJECT" --primer "$PRIMER" \
  --stream decoded.cm --output recovered.txt
```

`carrier-encode` reports `K_all`, visible characters, UTF-8 bytes, stream bytes,
and token counts. The active real-model round trip is recorded in
`tests/fixtures/mlx_llama32_3b_4bit/fixture.json`.

The normative implementation draft is [docs/protocol.md](docs/protocol.md).
