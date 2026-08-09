# Model profile

Covermail currently has one local candidate profile. It is not a general claim
that any similarly named model or runtime is compatible.

## Runtime

- profile: `darwin-arm64-mlx`;
- backend: MLX-LM with exact Metal top-logit retrieval;
- model: `mlx-community/Ministral-3-8B-Instruct-2512-4bit`;
- immutable revision: `182f003f01daa75f9de0f2c4d379722fd0bc1c61`;
- weights: MLX 4-bit, group size 64;
- architecture: 34 Ministral text layers, 131072-token vocabulary;
- Python and package versions: exact values in the address fixture;
- `trust_remote_code=false`;
- logits cast to float32.

The complete 131072-token logit vector remains on Metal. The adapter retrieves
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
`tests/fixtures/mlx_ministral3_8b_instruct_4bit/address.json`:

- digest: `6fe08caa6a72b092ef4badb3f6670be1bb5e7d164ce4681d123f9bf436d8fbe9`;
- selected token IDs: `[46634, 1033, 42239, 4098]`.

The committed three-case bundle records exact recovery of the continuous B/C
packet after an independently sampled A prefix; any following D is ignored.
The corpus, visible metrics and host timings are recorded in the fixture rather
than treated as protocol constants. The profile remains a local candidate until
the result is reproduced across two clean compatible installations.

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
