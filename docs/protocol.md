# Covermail protocol

Status: implementation draft. The repository defines one active WIP protocol;
there are no historical wire formats or compatibility shims.

## 1. Boundary

Covermail encrypts a UTF-8 message and maps the pseudorandom packet bytes to
language-model token choices. The LLM never encrypts or receives the secret.
Anyone with the public address, carrier, exact model and runtime can reconstruct
the public length header B and encrypted capsule C. The recipient private key is
required to authenticate and decrypt C.

There is no email-subject input in the protocol.

## 2. Carrier layout

The visible carrier has four logical regions:

```text
A: 64 observed prefix tokens
B: canonical public uvarint length header
C: one variable HPKE message capsule
D: optional unverified visible finish
```

B and C form one continuous arithmetic byte stream `B || C`. Their byte
boundary does not need to coincide with a token boundary.

## 3. Public address

The address is strict canonical JSON. It pins the recipient X25519 public key,
exact Ministral model revision and artifacts, runtime packages, cover persona,
candidate construction, arithmetic parameters, prompt `cm-packet-email`, 64
prefix tokens, and the model self-test. Unknown or missing fields fail closed.

SHA-256 of the canonical JSON is the address digest. Its first 16 bytes are the
human-independent address ID.

## 4. A — observed generated prefix

The sender supplies an arbitrary local writing brief to the prefix prompt. The
qualified tokenizer/model samples exactly 64 copy-safe visible tokens. These
tokens carry no hidden packet bits and are transmitted literally.

The writing brief, sampling seed and sampling policy are not protocol inputs.
The receiver observes A directly and never reconstructs its generation.

Before encoding B, the sender resets the model context. Both parties then use:

```text
fixed payload prompt || exact 64 token IDs of A
```

for the first arithmetic token and extend that same visible prefix thereafter.
The fixed payload prompt asks the model to preserve A's topic, people, tone,
point of view, tense and syntax while deferring conclusion and signoff until D.
It does not impose a target length or ask the model to invent new subtopics.
Both parties render this exact fixed prompt before decoding starts.

## 5. Prefix binding

The exact A token IDs are serialized as a uint16 count followed by uint32 token
IDs and hashed under `covermail/prefix-context\0`. The HPKE capsule binds:

```text
packet_label || address_digest || prefix_context_digest || exact_B
```

Changing A therefore changes both the language-model context and HPKE info.

## 6. C — encrypted message capsule

The sender packs the secret into a minimal inner frame containing flags, the
original UTF-8 length and either raw or DEFLATE body bytes. It encrypts that
frame once with HPKE Base:

```text
DHKEM_X25519_HKDF_SHA256 / HKDF_SHA256 / AES_128_GCM
info = packet_label || address_digest || prefix_context_digest || exact_B
```

The result C has 48 bytes of HPKE overhead. A 16-byte UI message identifier is
derived from SHA-256(C); it is not stored in the encrypted plaintext.

## 7. B — public length header

Before encrypting C, the sender computes its exact byte length from the inner
frame and HPKE overhead. B is the canonical unsigned LEB128 encoding of that
length. B is supplied as HPKE `info`, so any alteration fails authentication.
No visible marker or fixed token count is used for B.

## 8. Candidate table and frequencies

At each B/C position the implementation obtains float32 logits, quantizes
`round_half_even(logit * 1024)`, excludes special IDs, orders by quantized score
then token ID, filters the address-bound raw candidate pool for visible and
complete-prefix copy-safe tokens, and retains the fixed top-k.

Deterministic Decimal exponentiation at the address temperature produces
positive integer frequencies summing to 32768. LF is an ordinary eligible
visible token. There is no bridge, word blacklist, or fixed bits-per-token rule.

The copy-safe invariant is:

```text
tokenize(detokenize(prefix_ids || [candidate_id]))
    == prefix_ids || [candidate_id]
```

## 9. Continuous inverse arithmetic stream

The sender inverse-decodes `B || C` through the token candidate distributions
and mirrors the receiver's 32-bit arithmetic encoder. It stops only after every
real bit of both capsules is confirmed. Beyond the real byte boundary it reads
a sender-local random virtual suffix. These lookahead bits are not packet data,
need not be reproduced by the receiver and restore ordinary probabilistic
sampling after the final real bit has entered the arithmetic decoder.

The receiver first recovers enough complete bytes to parse canonical B. It then
changes the target to:

```text
8 * (len(B) + len(C))
```

without resetting arithmetic state. This is a byte boundary inside one stream,
analogous to framing a packet on TCP; one token may confirm bits on both sides
of the logical B/C boundary.

## 10. D — local finish

After all B/C bits are confirmed, the sender switches to the fixed local
finishing prompt and appends greedy copy-safe visible tokens. The default stops
on model EOS or after 128 tokens, whichever happens first.

D carries no bits, is not authenticated, is not reconstructed, and is not
validated by the receiver. The receiver stops model evaluation at the token
that completes B/C and ignores the remainder. Final user edits must preserve the
tokenization of A/B/C; the application can verify this locally before sending.

## 11. Decoding

The receiver:

1. canonicalizes CRLF/CR to LF and tokenizes the complete carrier;
2. takes tokens 0..63 as A;
3. renders the fixed payload prompt and appends A as assistant prefix;
4. runs the arithmetic encoder from token 64;
5. parses canonical B and learns `len(C)`;
6. continues the same arithmetic state until `len(B) + len(C)` bytes are complete;
7. ignores every remaining D token;
8. authenticates and decrypts C with the exact B, address and A token IDs;
9. validates and decompresses the inner frame.

Any mismatch inside A/B/C fails closed. D is outside that boundary by design.

## 12. Limits and policies

Wire-level fixed values are A=64 tokens, canonical B encoding, HPKE suite,
arithmetic precision and frequency total. Carrier-size guards,
generation timeouts, retry counts, D token budgets and lexical qualification
filters are local resource or product policies, not decoding rules.

## 13. Metrics

The principal metric is:

```text
K_all = visible Unicode code points / (len(B) + len(C))
```

Reports also distinguish A tokens, B/C arithmetic tokens, ignored D tokens,
UTF-8 carrier bytes and generation/decoding throughput.

## 14. Local application

The Stage 4 FastAPI development application remains loopback-only with no
session or Host/Origin gate, no permissive CORS, bounded JSON requests,
serialized MLX access and authenticated SSE progress. The write screen accepts
a public address, free writing brief and secret. The read screen needs only a
local identity, its passphrase and the exact carrier; there is no subject field.
