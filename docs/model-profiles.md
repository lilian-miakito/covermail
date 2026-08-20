# Model profile

Covermail currently has one local candidate profile. It is not a general claim
that any similarly named model or runtime is compatible.

## Runtime

- profile: `darwin-arm64-mlx`;
- backend: MLX-LM with exact Metal top-logit retrieval;
- model: `mlx-community/Qwen3.5-4B-4bit`;
- immutable revision: `0e7ffd5c629ef7719d4cbc04069232580bfa9d9c`;
- weights: MLX 4-bit, group size 64;
- architecture: 32 Qwen 3.5 text layers, 248320-token vocabulary;
- Python and package versions: exact values in the address fixture;
- `trust_remote_code=false`;
- logits cast to float32.

The complete 248320-token logit vector remains on Metal. The adapter retrieves
a growing top-logit superset and performs normative float32 quantization and
token-ID tie breaking on CPU. It expands the superset whenever the requested
boundary is tied, so the resulting candidate table is identical to a complete
CPU sort without transferring and sorting the full vocabulary.

The active self-test was generated on an Apple M3 Pro with 18 GB of memory,
macOS 26.7 and the exact runtime recorded in the address fixture. It fails
before carrier processing when the prompt, tokenizer, artifacts, runtime or
model logits differ.

## Codec configuration

- codec: `cm-arithmetic`;
- prompt: `cm-packet-email` with distinct English A, B/C and D phases;
- exactly 64 observed A tokens;
- raw candidate pool: 160 tokens;
- fixed top-k candidates: 20;
- no top-p;
- A sampling temperature: 1.0;
- B/C arithmetic temperature: 1.6;
- integer frequency total: 32768;
- no length bias;
- every valid table updates arithmetic state;
- sender-local random arithmetic lookahead after the final B/C bit;
- no protocol-bound D length (the CLI defaults to at most 128 greedy tokens).

Line feeds, spaces, punctuation, markup, and ordinary model vocabulary are not
removed merely because of their text. Special token IDs are excluded. A
candidate must be non-empty, UTF-8 serializable, free of CR and NUL, and must
round-trip with the complete visible token prefix.

The current model self-test is recorded in
`tests/fixtures/mlx_qwen35_4b_4bit/address.json`:

- digest: `5dfd5495624ceee24c01033e4d5cb7c096892cdbaaf1f8ba2db3a11fe982819e`;
- selected token IDs: `[18103, 8254, 1892, 271]`.

The deterministic self-test is current. A compact-packet carrier bundle is
still required for cross-installation evidence.

## Exact prompt roles

All instructions and cover-profile fields are English. The sender's free writing
brief appears only in the A prompt. It is never serialized and is not required
by the decoder.

The B/C prompt is fixed. It tells the model to continue the observed draft while
preserving topic, people, tone, point of view, tense and syntax; it forbids a
conclusion, signature, task commentary and unrelated filler. The decoder renders
this same prompt, appends the 64 observed A tokens, then replays each B/C token.

The D prompt asks for exactly one short closing sentence, a sign-off and a common
first name, with no new information or placeholder text. D is greedy, capped at
128 tokens and ignored by decoding.

The rendered B/C prompt is hashed into the model self-test transcript. Any change
to its text, punctuation, chat template, tokenizer, candidate parameters or
model logits changes the self-test and fails before carrier processing.
