# MLX Qwen 3.5 4B 4-bit local-candidate profile

This is public test data, not a real identity. Its X25519 private key is the
raw byte sequence `01 02 ... 20`, base64url
`AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA`.

- profile state: local candidate, not supported;
- qualification hardware: Apple M3 Pro, 18 GB, macOS 26.7, arm64;
- exact runtime and artifact hashes: `address.json`;
- self-test digest: `5dfd5495624ceee24c01033e4d5cb7c096892cdbaaf1f8ba2db3a11fe982819e`;
- self-test selected token IDs: `[18103, 8254, 1892, 271]`.

The address is the single active Covermail profile. Its deterministic payload
self-test is current. A compact-packet qualification bundle has not been
generated.

Candidate construction stops after the fixed 20 copy-safe survivors. The
address self-test binds the prompt, tokenizer, model artifacts, runtime and
selected token path.

Carrier strings are stored directly in JSON; escaped LF characters remain
protocol data.
