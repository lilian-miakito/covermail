# MLX Qwen3.5 4B 4-bit local-candidate profile

This is public test data, not a real identity. Its X25519 private key is the
raw byte sequence `01 02 ... 20`, base64url
`AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA`.

- profile state: local candidate, not supported;
- qualification hardware: Apple M3 Pro, 18 GB, macOS 26.6, arm64;
- exact runtime and artifact hashes: `address.json`;
- self-test digest: `061e0f5d86d5d62ce4e62c3b0df65af8664915197bce4f9c334678dccee1bb52`;
- self-test selected token IDs: `[16737, 84, 9473, 11]`.

The address is the single active Covermail profile. `qualification.json`
records three complete real-model round trips using distinct sender-only
writing briefs. Each carrier consists of sampled A, one continuous arithmetic
encoding of encrypted B and C, then a locally generated D ignored by decoding.
The JSON file is the source of truth for host-dependent token counts, `K_all`
and timings.

- `garden`: 150 packet bytes, 710 tokens, `K_all=18.4333`, 25.65 s encode;
- `journey`: 169 packet bytes, 777 tokens, `K_all=18.4201`, 27.90 s encode;
- `dinner`: 171 packet bytes, 767 tokens, `K_all=18.4503`, 28.08 s encode;
- accepted throughput: 27.3–27.9 tokens/s;
- all three cases passed on their first trial with A=64 and no lexical flag;
- lexical signals are observations only and never reject exact B/C recovery.

The same host also passes the portable foreign-bundle verification path for all
three packets. This is not yet cross-installation evidence.

An exhaustive 248320-logit reference sort and the accelerated Metal retrieval
produced the same exact ranking. Candidate construction now stops after the
fixed 20 copy-safe survivors instead of retokenizing the remainder of the raw
pool; the address self-test remains exact.

Carrier strings are stored directly in JSON; escaped LF characters remain
protocol data.
