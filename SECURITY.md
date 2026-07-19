# Security policy

Covermail is an experimental implementation and has not received an independent
security review. Do not treat it as production security software.

Please report vulnerabilities privately to the repository owner rather than
opening a public issue. Reports should avoid including real private keys,
passphrases, secret plaintext, or complete hidden payloads.

The cryptographic boundary is RFC 9180 HPKE as provided by `cryptography` 49;
the future generative layer is camouflage, not encryption. The threat model and
release checklist are normative in [`docs/protocol.md`](docs/protocol.md).
