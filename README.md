# Covermail

Covermail is an experimental, stateless, recipient-oriented generative
steganography protocol. This repository is a clean MIT implementation; it does
not reuse source code from the GPL `conversation-steganography` project.

The current implementation covers Stages 0 through 2 of
[`docs/protocol.md`](docs/protocol.md): strict public addresses, fingerprints,
encrypted X25519 identities, bounded inner framing/compression, RFC 9180 HPKE
Base, outer framing, the deterministic 32-bit arithmetic codec, and a fake-model
carrier harness. It deliberately does **not** yet implement a real language
model, a plausible email carrier, or the web UI.

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

## License

MIT. See [LICENSE](LICENSE).
