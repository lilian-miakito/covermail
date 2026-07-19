# Covermail

Covermail is an experimental, stateless, recipient-oriented generative
steganography protocol. This repository is a clean MIT implementation; it does
not reuse source code from the GPL `conversation-steganography` project.

The current implementation covers only Stages 0 and 1 of
[`docs/protocol.md`](docs/protocol.md): strict public addresses, fingerprints,
encrypted X25519 identities, bounded inner framing/compression, RFC 9180 HPKE
Base, outer framing, and an offline binary CLI. It deliberately does **not** yet
implement the language model, arithmetic codec, carrier text, or web UI.

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
tokens; it is not an email body.

## License

MIT. See [LICENSE](LICENSE).
