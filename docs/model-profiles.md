# Model profiles

## Qualification states

A profile is **local-candidate** after its artifacts, prompt, adapter, and
self-test pass on one installation. It is **supported** only after the Stage 3
cross-installation fixtures in `docs/protocol.md` section 29.5 pass. Code and
documentation must not describe a local-candidate profile as supported.

The old example address remains a schema-only placeholder. It must fail model
artifact preparation and compatibility checks.

## `darwin-arm64-mlx-v1` local candidate

The first Stage 3 candidate deliberately has a narrow compatibility claim:

- OS/architecture class: macOS on Apple silicon (`darwin-arm64`);
- Python: exact patch version recorded in each address (initial qualification:
  `3.12.5`);
- backend packages: `mlx==0.31.2`, `mlx-lm==0.31.3`;
- backend: MLX inference only, direct full-vocabulary logits, exported as
  IEEE-754 float32; no sampling API; sequential calls use MLX's ordinary
  prompt KV cache and reset it whenever the context is not the previous context
  plus exactly one token;
- model: `mlx-community/Llama-3.2-3B-Instruct-4bit` at immutable revision
  `7f0dc925e0d0afb0322d96f9255cfddf2ba5636e`;
- weights: MLX 4-bit safetensors only; `trust_remote_code=false`;
- codec defaults under qualification: `top_n=64`, candidate-pool multiplier
  `8`, temperature milli `1000`, length-bias milli `100`, and 32 finishing
  tokens.

`top_n=64` is an intentional first-profile choice rather than a protocol
change. It keeps the reference full-prefix copy-safe check measurable while
retaining up to six raw coding bits per token. Capacity and quality measurements
remain required before changing it.

### Deterministic chat-template rule

The pinned tokenizer template calls `strftime_now` when it is not supplied a
date. The adapter must therefore pass `date_string="26 Jul 2024"` explicitly to
`apply_chat_template`. This exact constant belongs to the profile. Rendering
must never read the clock, locale, hostname, or other ambient state.

All free-text cover fields and the canonical subject are inserted as compact
JSON string literals. Before JSON encoding, the exact substitutions are
`<|` -> `< |` and `|>` -> `| >`.

### Qualified artifact tree

Hugging Face snapshot directories use symlinks into a blob store. They are a
trusted download source, not a directly usable address-controlled artifact
tree: Covermail verification never follows symlinks. A preparation step must
materialize the consumed files below into a user-chosen profile directory as
ordinary regular files (APFS clones or hard links are acceptable), then build
the address manifest from that directory:

- `config.json`;
- `model.safetensors`;
- `model.safetensors.index.json`;
- `special_tokens_map.json`;
- `tokenizer.json`;
- `tokenizer_config.json`.

Every listed file is size- and SHA-256-verified before load. The model root is
selected by the local user/configuration and is not derived as an arbitrary
filesystem path from the address.

### Remaining qualification work

The candidate becomes supported only after:

1. a real self-test digest and fixture are committed;
2. capacity and wall-time measurements are recorded;
3. generation and recovery pass on two clean compatible installations;
4. each installation decodes the other installation's independently generated
   carrier.
