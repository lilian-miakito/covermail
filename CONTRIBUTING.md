# Contributing

Read [`docs/protocol.md`](docs/protocol.md) in full before changing protocol
code. Preserve wire formats exactly and flag contradictions before changing the
specification. Contributions must be original MIT-compatible work and must not
copy code from `conversation-steganography`.

Run `uv run pytest`, `uv run ruff check .`, and `uv run mypy` before submitting
changes. Protocol changes require fixtures and adversarial tests.
