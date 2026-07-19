# Model profiles

## Qualification states

A profile is **local-candidate** after its artifacts, prompt, adapter, and
self-test pass on one installation. It is **supported** only after the Stage 3
cross-installation fixtures in `docs/protocol.md` section 29.5 pass. Code and
documentation must not describe a local-candidate profile as supported.

The old example address remains a schema-only placeholder. It must fail model
artifact preparation and compatibility checks.

## `darwin-arm64-mlx-v1` runtime

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
- current codec defaults under qualification: `cm-arithmetic-v2`, `top_n=64`,
  candidate-pool multiplier `8`, temperature milli `1000`, zero length bias,
  and 32 finishing tokens.

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

## `cm-arithmetic-v2` current local candidate

V2 is the single forward implementation. V1 fixtures remain only as regression
evidence. V2 adds an exact first-sentence primer chosen by Bob, authenticates the
canonical subject and primer in HPKE `info`, begins the coded stream with the
random 32-byte HPKE encapsulated key, and masks every structured byte after it.

The prompt continues the visible primer without a sentence limit. Candidate
construction preserves the qualified relative logits with temperature 1 and
zero visible-length penalty. It retains the existing deterministic top-512
pool, visible/copy-safe filters, final top 64, 75% low-entropy bridge rule, and
top-1 sentence closure.

The exact fixture address is
`tests/fixtures/mlx_llama32_3b_4bit_v2/address.json`. Its self-test digest is
`ae035e8b95af629d5f552ed9e8635fb3e66b9f2fed03521978b77426552340a5`.
On the qualification M3 Pro, a 114-byte stream produced 1318 visible Unicode
characters, including primer and closure:

```text
K_all = 1318 / 114 = 11.5614 characters per stream byte
```

This single empirical point used 18 primer, 250 data, 81 bridge, and 10 finish
tokens. Cross-installation qualification remains outstanding.
