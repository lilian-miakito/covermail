# Interoperability status

The pure protocol and fake-model layers round-trip practical payloads through
the continuous 32-bit inverse arithmetic coder without bridge states. The
automated suite covers canonical B framing, variable C recovery, HPKE, A/B
binding, tokenizer round trips, LF carrier text, ignored D tails and CLI/UI
orchestration.

The MLX profile passes its deterministic self-test on the local qualification
host. Its exact artifacts and runtime are pinned in the public address fixture.
Real-model qualification bundles exercise fixed writing briefs with freshly
sampled A prefixes and exact byte-for-byte recovery of B and C. D is neither
reconstructed nor compared.

`covermail model-qualify` implements the cross-installation exchange. A bundle
contains each visible carrier, exact A token IDs, the B header and encrypted C
bytes, but no private key or hidden plaintext. Verification rebuilds the fixed
payload model context from the observed A tokens, decodes B/C and compares the
packet bytes.
Lexical signals are reported but never determine packet validity.

No current real-model qualification bundle is committed. A compact-packet
bundle must be generated and exchanged before interoperability is claimed.

Before claiming interoperability:

1. reproduce the self-test and candidate construction on another clean host;
2. verify the first host's bundle on the second host;
3. generate a fresh bundle on the second host and verify it on the first;
4. review visible prose quality separately from bit-exact interoperability.
