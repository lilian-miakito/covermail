# Interoperability status

Stages 0 through 2 are implemented for Python 3.12 with `cryptography==49.0.0`.
Binary exchange uses the exact inner, HPKE, outer payload, and stego framing from
the protocol. The HPKE suite is checked against RFC 9180 Appendix A.1 inputs;
because the selected single-shot API has no AAD parameter, the fixture uses the
published sequence-0 key and nonce with empty AAD. The deterministic fake model
round-trips arbitrary practical payloads through the v1 32-bit arithmetic coder
and has a stored carrier fixture. The example JSON remains a structural template
rather than a publishable generative address.

Stage 3 now has one current **local-candidate**, not supported, codec:
`cm-arithmetic-v2` on `darwin-arm64-mlx-v1`, using the exact cached
`mlx-community/Llama-3.2-3B-Instruct-4bit` revision recorded in
`docs/model-profiles.md`. Artifact verification, pure prompt rendering, full
candidate construction, copy-safe/visible filters, the four-state self-test,
MLX direct logits, a real encrypted frame/carrier fixture, and CLI encode/decode
paths are implemented.

The v2 M3 Pro round trip recovered and decrypted the stream exactly. It uses a
Bob-chosen visible first sentence, binds that primer and the subject through
HPKE, and uniformizes framing before arithmetic coding. A 114-byte stream used
359 total carrier tokens and 1318 visible characters. Empirical `K_all` is
11.5614 Unicode characters per stream byte, including primer, bridges, data,
and closure. Reference times were 114.3 seconds to encode and 114.7 seconds to
decode. This is transport and steering evidence, not a cross-installation or
cover-quality claim.

The next Stage 3 qualification work is:

1. profile and optimize candidate construction without changing its exact
   output, especially full-vocabulary quantization and copy-safe checks;
2. collect `K_all` and quality measurements over representative message sizes;
3. qualify the selected larger/faster production model if this 3B profile is
   insufficiently fluent;
4. exchange independently generated v2 carriers across two clean compatible
   installations.

No real-model interoperability or cover-quality claim is made until all four
items pass.
