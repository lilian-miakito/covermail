# Model profile

Covermail currently has one local candidate profile. It is not a general claim
that any similarly named model or runtime is compatible.

## Runtime

- profile: `darwin-arm64-mlx`;
- backend: MLX-LM with direct full-vocabulary logits;
- model: `mlx-community/Llama-3.2-3B-Instruct-4bit`;
- immutable revision: `7f0dc925e0d0afb0322d96f9255cfddf2ba5636e`;
- weights: MLX 4-bit, group size 64;
- Python and package versions: exact values in the address fixture;
- `trust_remote_code=false`;
- logits cast to float32.

## Codec configuration

- codec: `cm-arithmetic`;
- prompt: `cm-email-continuation`;
- raw candidate pool: 512 tokens;
- final candidates: 64;
- temperature: 1;
- integer frequency total: 32768;
- no length bias;
- every valid table updates arithmetic state;
- up to 32 greedy finishing tokens.

Line feeds, spaces, punctuation, markup, and ordinary model vocabulary are not
removed merely because of their text. Special token IDs are excluded. A
candidate must be non-empty, UTF-8 serializable, free of CR and NUL, and must
round-trip with the complete visible token prefix.

The current model self-test is recorded in
`tests/fixtures/mlx_llama32_3b_4bit/address.json`:

- digest: `696baa21246bef6026ae86fce59e7f8b4116a74f525db56b8e137e98b6e9bf13`;
- selected token IDs: `[2998, 16968, 47838, 14896]`.

The profile remains a local candidate until a complete carrier is generated
and decoded in practical time on at least two clean compatible installations.
