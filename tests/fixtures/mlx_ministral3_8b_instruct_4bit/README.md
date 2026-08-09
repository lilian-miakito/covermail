# MLX Ministral 3 8B Instruct 4-bit local-candidate profile

This is public test data, not a real identity. Its X25519 private key is the
raw byte sequence `01 02 ... 20`, base64url
`AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA`.

- profile state: local candidate, not supported;
- qualification hardware: Apple M3 Pro, 18 GB, macOS 26.6, arm64;
- exact runtime and artifact hashes: `address.json`;
- self-test digest: `6fe08caa6a72b092ef4badb3f6670be1bb5e7d164ce4681d123f9bf436d8fbe9`;
- self-test selected token IDs: `[46634, 1033, 42239, 4098]`.

The address is the single active Covermail profile. Its deterministic payload
self-test is current. A compact-packet qualification bundle has not been
generated.

An exhaustive 131072-logit reference sort and the accelerated Metal retrieval
produced the same exact ranking. Candidate construction now stops after the
fixed 20 copy-safe survivors instead of retokenizing the remainder of the raw
pool; the address self-test remains exact.

Carrier strings are stored directly in JSON; escaped LF characters remain
protocol data.
