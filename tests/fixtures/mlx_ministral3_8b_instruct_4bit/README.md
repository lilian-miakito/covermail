# MLX Ministral 3 8B Instruct 4-bit local-candidate profile

This is public test data, not a real identity. Its X25519 private key is the
raw byte sequence `01 02 ... 20`, base64url
`AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA`.

- profile state: local candidate, not supported;
- qualification hardware: Apple M3 Pro, 18 GB, macOS 26.6, arm64;
- exact runtime and artifact hashes: `address.json`;
- self-test digest: `6fe08caa6a72b092ef4badb3f6670be1bb5e7d164ce4681d123f9bf436d8fbe9`;
- self-test selected token IDs: `[46634, 1033, 42239, 4098]`.

The address is the single active Covermail profile. `qualification.json`
records three complete real-model round trips using distinct sender-only
writing briefs. Each carrier consists of sampled A, one continuous arithmetic
encoding of encrypted B and C, then a locally generated D ignored by decoding.
The JSON file is the source of truth for host-dependent token counts, `K_all`
and timings.

- `garden`: 163 packet bytes, 495 tokens, `K_all=13.0368`, 25.73 s encode;
- `journey`: 164 packet bytes, 480 tokens, `K_all=12.2073`, 26.98 s encode;
- `dinner`: 161 packet bytes, 465 tokens, `K_all=12.7019`, 26.06 s encode;
- accepted throughput: 17.8–19.2 tokens/s;
- all three cases passed on their first trial with A=64 and no lexical flag;
- lexical signals are observations only and never reject exact B/C recovery.

The same host also passes the portable foreign-bundle verification path for all
three packets. This is not yet cross-installation evidence.

An exhaustive 131072-logit reference sort and the accelerated Metal retrieval
produced the same exact ranking. Candidate construction now stops after the
fixed 20 copy-safe survivors instead of retokenizing the remainder of the raw
pool; the address self-test remains exact.

Carrier strings are stored directly in JSON; escaped LF characters remain
protocol data.
