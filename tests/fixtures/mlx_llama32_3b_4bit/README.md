# MLX Llama 3.2 3B 4-bit local-candidate fixture

This fixture is public test data, not a real identity. Its X25519 private key is
the raw byte sequence `01 02 ... 20`, encoded as
`AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA`.

- profile state: local candidate, not supported;
- subject: `Des nouvelles du jardin`;
- plaintext: `On se retrouve jeudi à 18 h.`;
- qualification hardware: Apple M3 Pro, 18 GB, macOS 26.6, arm64;
- exact runtime and artifact hashes: `address.json`;
- self-test selected token IDs: `[30854, 757, 55353, 2852]`;
- self-test reference wall time: 1.4 s after model load;
- model load reference wall time: 3.0 s.

`fixture.json` and `carrier.txt` record an actual bit-exact round trip on that
installation. The 114-byte encrypted frame became a 301-token, 1021-character
carrier. Reference wall times were 98.6 s to encode and 96.6 s to decode.

The result proves transport integrity, not acceptable cover quality. It is too
long, exceeds the prompted sentence budget, and contains implausible phrases.
Performance and carrier selection/quality are therefore open qualification
blockers. Cross-installation exchange is also still required before this
profile can be called supported.
