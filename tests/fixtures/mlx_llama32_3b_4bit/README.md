# MLX Llama 3.2 3B 4-bit local-candidate profile

This is public test data, not a real identity. Its X25519 private key is the
raw byte sequence `01 02 ... 20`, base64url
`AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA`.

- profile state: local candidate, not supported;
- qualification hardware: Apple M3 Pro, 18 GB, macOS 26.6, arm64;
- exact runtime and artifact hashes: `address.json`;
- self-test digest: `696baa21246bef6026ae86fce59e7f8b4116a74f525db56b8e137e98b6e9bf13`;
- self-test selected token IDs: `[2998, 16968, 47838, 14896]`.

The address is the single active Covermail profile. `fixture.json` records a
complete real-model encode/decode/HPKE round trip for the active codec:

- stream: 114 bytes / 912 bits;
- carrier: 391 tokens, 1413 Unicode characters, 1454 UTF-8 bytes;
- composition: 18 primer, 345 arithmetic, and 28 finish tokens;
- internal line feeds: 10;
- `K_all`: 12.3947 characters per stream byte;
- encode: 132.13 s; decode: 129.62 s on the qualification host.

The carrier is stored as base64 because exact whitespace, including an internal
space immediately before LF, is protocol data.
