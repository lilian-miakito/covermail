# Covermail

Covermail is an experimental, stateless, recipient-oriented generative
steganography protocol. This repository is a clean MIT implementation; it does
not reuse source code from the GPL `conversation-steganography` project.

The current implementation covers Stages 0 through 2 and a local Stage 3 model
candidate from
[`docs/protocol.md`](docs/protocol.md): strict public addresses, fingerprints,
encrypted X25519 identities, bounded inner framing/compression, RFC 9180 HPKE
Base, outer framing, the deterministic 32-bit arithmetic codec, and a fake-model
carrier harness. The Stage 3 MLX profile completes a bit-exact real-model round
trip, but its measured prose is not yet plausible enough to call the profile
supported. The web UI is deliberately not implemented.

Covermail is experimental camouflage providing plausible deniability. It does
not promise undetectability, endpoint security, anonymity, forward secrecy, or
protection against address substitution. Verify the full address fingerprint
over an authenticated channel.

## Development

Python 3.12 and `uv` are required.

```console
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run mypy
```

The optional MLX profile is installed explicitly:

```console
uv sync --extra dev --extra mlx
```

## Stage 1 binary round trip

The example address is a structural Stage 1 template only. Its placeholder
model manifest and self-test do not qualify it for future generative use.

```console
uv run covermail identity-create covermail.example.json \
  --identities-dir .covermail/identities \
  --public-address alice.covermail.json
uv run covermail encrypt alice.covermail.json --message secret.txt --output message.cm
uv run covermail decrypt .covermail/identities/ADDRESS_ID \
  --frame message.cm --output recovered.txt
```

Passphrases are prompted without command-line arguments. The `message.cm`
binary output is the exact stego frame that Stage 2 will later map to carrier
tokens; it is not itself an email body.

## Stage 2 fake-carrier round trip

The fake model exercises the exact bitstream, arithmetic termination, bridge,
finish-token, and retokenization rules. Its output is intentionally synthetic
and must not be mistaken for a plausible cover email.

```console
uv run covermail fake-encode --frame message.cm --output carrier.fake.txt
uv run covermail fake-decode --carrier carrier.fake.txt --output decoded.cm
cmp message.cm decoded.cm
uv run covermail decrypt .covermail/identities/ADDRESS_ID \
  --frame decoded.cm --output recovered-via-carrier.txt
```

`cmp` produces no output when the recovered binary frame is exact. The fake
model is deterministic, so the same input frame always produces the same fake
carrier fixture.

## Stage 3 MLX cm-arithmetic-v2 local candidate

The exact profile and its current limitations are documented in
[`docs/model-profiles.md`](docs/model-profiles.md). Prepare an already downloaded
snapshot into a new no-symlink qualified tree, then use the committed public test
address to verify compatibility:

```console
uv run covermail model-prepare \
  --source /path/to/exact/huggingface/snapshot \
  --destination .covermail/models/llama32-3b-4bit
uv run covermail model-self-test \
  tests/fixtures/mlx_llama32_3b_4bit_v2/address.json \
  --model-root .covermail/models/llama32-3b-4bit \
  --subject "Des nouvelles du jardin" \
  --primer "Je voulais te raconter calmement ce qui est arrivé au jardin."
```

Create a v2 identity from that public template, then encrypt with the exact
subject and visible first-sentence primer:

```console
uv run covermail identity-create \
  tests/fixtures/mlx_llama32_3b_4bit_v2/address.json \
  --identities-dir .covermail/identities-v2 \
  --public-address alice-v2.covermail.json
uv run covermail encrypt-v2 alice-v2.covermail.json \
  --subject "Des nouvelles du jardin" \
  --primer "Je voulais te raconter calmement ce qui est arrivé au jardin." \
  --message secret.txt --output message.cm2
uv run covermail carrier-encode alice-v2.covermail.json \
  --model-root .covermail/models/llama32-3b-4bit \
  --subject "Des nouvelles du jardin" \
  --primer "Je voulais te raconter calmement ce qui est arrivé au jardin." \
  --frame message.cm2 --output carrier.v2.txt
uv run covermail carrier-decode alice-v2.covermail.json \
  --model-root .covermail/models/llama32-3b-4bit \
  --subject "Des nouvelles du jardin" \
  --carrier carrier.v2.txt --output decoded.cm2 \
  --primer-output decoded-primer.txt
uv run covermail decrypt-v2 .covermail/identities-v2/ADDRESS_ID \
  --subject "Des nouvelles du jardin" \
  --primer "Je voulais te raconter calmement ce qui est arrivé au jardin." \
  --stream decoded.cm2 --output recovered-v2.txt
```

`carrier-encode` reports `k_all`, defined as every visible Unicode character
(primer, bridge, data, and finish) divided by the v2 stream byte count. The
committed 114-byte fixture measured `K_all = 11.5614`.

Model preparation is the only step that may use a trusted downloaded snapshot.
Sending and receiving load the qualified local tree offline. The committed real
fixture is public test data and must not be used as an identity.

## License

MIT. See [LICENSE](LICENSE).
