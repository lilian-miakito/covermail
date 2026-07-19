# Interoperability status

Stages 0 through 2 are implemented for Python 3.12 with `cryptography==49.0.0`.
Binary exchange uses the exact inner, HPKE, outer payload, and stego framing from
the protocol. The HPKE suite is checked against RFC 9180 Appendix A.1 inputs;
because the selected single-shot API has no AAD parameter, the fixture uses the
published sequence-0 key and nonce with empty AAD. The deterministic fake model
round-trips arbitrary practical payloads through the v1 32-bit arithmetic coder
and has a stored carrier fixture. The example JSON remains a structural template
rather than a publishable generative address.

Stage 3 now has one **local-candidate**, not supported, profile:
`darwin-arm64-mlx-v1` using the exact cached
`mlx-community/Llama-3.2-3B-Instruct-4bit` revision recorded in
`docs/model-profiles.md`. Artifact verification, pure prompt rendering, full
candidate construction, copy-safe/visible filters, the four-state self-test,
MLX direct logits, a real encrypted frame/carrier fixture, and CLI encode/decode
paths are implemented.

The first M3 Pro round trip recovered and decrypted the frame exactly. A
114-byte encrypted frame required 301 carrier tokens, 61 low-entropy bridge
tokens, 1021 visible characters, 98.6 seconds to encode, and 96.6 seconds to
decode. The generated prose is too long and insufficiently plausible. This is
evidence of transport correctness only, not successful camouflage.

The next Stage 3 qualification work is:

1. profile and optimize candidate construction without changing its exact
   output, especially full-vocabulary quantization and copy-safe checks;
2. add carrier trials and deterministic quality selection from protocol
   section 20;
3. remeasure capacity, latency, sentence-budget adherence, and plausibility;
4. exchange independently generated carriers across two clean compatible
   installations.

No real-model interoperability or cover-quality claim is made until all four
items pass.
