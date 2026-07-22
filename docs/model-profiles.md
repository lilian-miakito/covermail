# Model profile

Covermail currently has one local candidate profile. It is not a general claim
that any similarly named model or runtime is compatible.

## Runtime

- profile: `darwin-arm64-mlx`;
- backend: MLX-LM with exact Metal top-logit retrieval;
- model: `mlx-community/Qwen3.5-4B-4bit`;
- immutable revision: `0e7ffd5c629ef7719d4cbc04069232580bfa9d9c`;
- weights: MLX 4-bit, group size 64;
- architecture: 24 Gated DeltaNet and 8 full-attention layers;
- Python and package versions: exact values in the address fixture;
- `trust_remote_code=false`;
- logits cast to float32.

The complete 248320-token logit vector remains on Metal. The adapter retrieves
a growing top-logit superset and performs normative float32 quantization and
token-ID tie breaking on CPU. It expands the superset whenever the requested
boundary is tied, so the resulting candidate table is identical to a complete
CPU sort without transferring and sorting the full vocabulary.

On the qualification host, a reference self-test distribution produced the
same exact top 512 token IDs and quantized scores with both paths. Retrieval
plus prefill took 0.475 s with the Metal path versus 0.941 s with exhaustive
transfer and sorting (1.98x for that measured step).

## Codec configuration

- codec: `cm-arithmetic`;
- prompt: `cm-packet-email` with distinct A, B/C and D phases;
- exactly 64 observed A tokens;
- raw candidate pool: 160 tokens;
- fixed top-k candidates: 20;
- no top-p;
- temperature: 1.0;
- integer frequency total: 32768;
- no length bias;
- every valid table updates arithmetic state;
- sender-local random arithmetic lookahead after the final B/C bit;
- no protocol-bound D length (the CLI currently defaults to 64 greedy tokens).

Line feeds, spaces, punctuation, markup, and ordinary model vocabulary are not
removed merely because of their text. Special token IDs are excluded. A
candidate must be non-empty, UTF-8 serializable, free of CR and NUL, and must
round-trip with the complete visible token prefix.

The current model self-test is recorded in
`tests/fixtures/mlx_qwen35_4b_4bit/address.json`:

- digest: `061e0f5d86d5d62ce4e62c3b0df65af8664915197bce4f9c334678dccee1bb52`;
- selected token IDs: `[16737, 84, 9473, 11]`.

The committed three-case bundle records exact recovery of the continuous B/C
packet after an independently sampled A prefix; any following D is ignored.
Accepted carriers contain 710–777 tokens, reach `K_all = 18.4201..18.4503` and
encode at 27.3–27.9 tokens/s on the qualification host. With the 64-token A and
fixed 1,200-word horizon, all three cases completed on their first trial with no
lexical flags; the earlier short-horizon prompt had produced two 4096-step
low-entropy tails. These are host
observations, not protocol constants. The profile
remains a local candidate until the result is reproduced across two clean
compatible installations.
