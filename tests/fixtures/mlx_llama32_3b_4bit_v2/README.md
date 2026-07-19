# MLX Llama 3.2 3B 4-bit cm-arithmetic-v2 fixture

This is public test data, not a real identity. Its X25519 private key is the raw
byte sequence `01 02 ... 20`, base64url
`AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA`.

- profile state: local candidate, not cross-installation supported;
- self-test digest: `ae035e8b95af629d5f552ed9e8635fb3e66b9f2fed03521978b77426552340a5`;
- self-test selected token IDs: `[2998, 16968, 91507, 11]`;
- primer tokens in the self-test: 11;
- self-test reference wall time: 1.4 s after model load.

The committed real round trip uses the same small public plaintext as the v1
fixture and binds its subject and primer through HPKE.

- v2 stream: 114 bytes / 912 bits;
- visible result: 359 tokens, 1318 Unicode characters, 1352 UTF-8 bytes;
- composition: 18 primer, 250 data, 81 bridge, and 10 finish tokens;
- `K_all`: 11.5614 visible characters per stream byte;
- UTF-8 byte ratio: 11.8596 carrier bytes per stream byte;
- payload rates: 3.648 bits/data token and 2.5404 bits/all visible token;
- reference wall time: 114.3 s encode, 114.7 s decode.

`K_all` deliberately includes primer, bridges, data, and finish tokens. This is
one empirical point for the exact fixture, not a population estimate.
