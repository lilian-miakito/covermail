# Covermail protocol

Status: implementation draft. The repository is pre-release and defines one
active protocol. Historical wire formats and compatibility branches are not
part of the implementation.

## 1. Purpose and boundaries

Covermail encrypts a UTF-8 message for a recipient, converts the resulting
pseudorandom byte stream into language-model token choices, and emits the
detokenized text as an email carrier.

The LLM does not encrypt the secret. Anyone with the public address, exact
model profile, subject, and carrier can in principle recover the HPKE
ciphertext. Only the recipient's private key reveals the plaintext.

The implementation does not promise resistance to traffic analysis, arbitrary
carrier edits, model fingerprinting, or a detector trained against its output.

## 2. Public address

An address is strict canonical JSON with these top-level fields:

```text
format, version, recipient, hpke, model, codec, cover
```

Unknown and missing fields are rejected. The active codec fields are fixed to:

```text
id                 = cm-arithmetic
prompt_template    = cm-email-continuation
visible_filter     = cm-visible-email
frequency_total    = 32768
logit_scale        = 1024
```

The model revision, artifacts, hashes, runtime packages, candidate count,
temperature, finish limit, self-test, and cover persona are address-bound.

The address digest is SHA-256 over canonical address JSON. Its first 16 bytes
form the address ID embedded in the outer payload.

## 3. Visible context

The visible subject is NFC-normalized, has repeated ASCII spaces/tabs collapsed
to one space, and is limited to 256 UTF-8 bytes. CR, LF, and NUL are invalid in
the subject.

The sender supplies an exact first-sentence primer. It must:

- contain 1..512 UTF-8 bytes;
- have no leading or trailing whitespace;
- contain no CR, LF, tab, NUL, invalid Unicode, or model-control delimiter;
- contain exactly one character from `.?!`, at its end;
- round-trip exactly through the qualified tokenizer.

The carrier is:

```text
primer || arithmetic continuation || greedy finish
```

The primer carries no hidden bits but initializes the model's visible context.

The context digest is SHA-256 over:

```text
"covermail/visible-context\0"
|| uint16_be(len(subject_utf8)) || subject_utf8
|| uint16_be(len(primer_utf8))  || primer_utf8
```

## 4. Encryption

The fixed HPKE suite is:

```text
KEM  = DHKEM_X25519_HKDF_SHA256
KDF  = HKDF_SHA256
AEAD = AES_128_GCM
mode = BASE
```

The compressed authenticated inner frame contains a random message ID and the
UTF-8 plaintext. HPKE `info` is:

```text
"covermail/hpke\0"
|| address_digest
|| outer_header
|| context_digest
```

Thus the exact address, subject, and primer are authenticated.

## 5. Uniformized stream

Split the HPKE result into the 32-byte encapsulated key `enc` and authenticated
ciphertext. Construct:

```text
payload = outer_header || hpke_ciphertext
tail = uvarint(len(payload)) || payload
mask = HKDF-SHA256(
    ikm=enc,
    salt=address_digest,
    info="covermail/stego-mask\0" || context_digest,
    length=len(tail),
)
stream = enc || (tail XOR mask)
```

The mask uniformizes structured bytes; it is public and adds no confidentiality.
After recovering 32 bytes, the decoder derives the mask, parses the length, and
knows the exact arithmetic termination target.

## 6. Prompt

Prompt `cm-email-continuation` asks the exact qualified model to continue the
visible primer on the visible subject for as long as necessary. It requests
ordinary personal email prose and permits natural paragraphs and LF line
breaks. The secret and ciphertext are never included in the prompt.

Prompt rendering uses the model's pinned chat template and a fixed date. Prompt
text, tokenizer, model artifacts, runtime, and logits are covered by the model
self-test.

## 7. Candidate table

At every continuation position:

1. obtain the complete next-token logit vector;
2. cast each finite logit to IEEE-754 float32;
3. quantize `round_half_even(logit * 1024)`;
4. exclude model special token IDs;
5. order by quantized logit descending, then token ID ascending;
6. take the raw top `top_n * candidate_pool_multiplier` tokens;
7. keep candidates whose text is non-empty, UTF-8 serializable, and contains
   neither CR nor NUL;
8. require the complete-prefix copy-safe property;
9. take the first `top_n` survivors.

The copy-safe property is:

```text
tokenize(detokenize(prefix_ids || [candidate_id]))
    == prefix_ids || [candidate_id]
```

It is necessary because the receiver observes text, not the sender's token IDs.
LF, tabs, spaces, punctuation, markup, and ordinary vocabulary are otherwise
eligible. There is no word blacklist.

## 8. Frequencies

Let quantized scores be `q_i`, maximum `q_max`, and temperature integer `T` in
thousandths. Deterministic Decimal arithmetic computes:

```text
x_i = (q_i - q_max) * 1000 / (1024 * T)
w_i = max(1, round_half_even(exp(x_i) * 2^24))
```

Positive integer counts are allocated proportionally by largest remainder and
sum exactly to 32768. At temperature 1000, the relative candidate probabilities
approximate the model's selected logits at temperature 1.

Every valid table is used by the arithmetic coder. There is no low-entropy
special case and no token that advances the model while skipping arithmetic
state. Highly probable choices may confirm zero bits immediately; their
fractional information remains in the interval state.

## 9. Inverse arithmetic coding

The coder uses an unsigned 32-bit range with the standard half, quarter, and
three-quarter renormalization boundaries.

The sender treats the stream bits as the arithmetic code value and repeatedly
decodes it into candidate indices. The receiver observes those candidate
indices and runs the matching arithmetic encoder to recover confirmed bits.

Bytes are read most-significant bit first. Beyond the real stream boundary the
sender exposes the virtual suffix:

```text
1, 0, 1, 0, ...
```

The sender runs a mirrored arithmetic encoder beside the symbol decoder and
stops only after the mirror has confirmed every real stream bit. Any confirmed
bits beyond the target must match the virtual suffix.

There is no fixed number of payload bits per token. A token's sequence-level
information is approximately `-log2(p)`, and confirmed bits can arrive in
bursts after several zero-output symbols.

## 10. Finishing

Once every real bit is confirmed, the sender repeatedly chooses candidate index
zero until the visible carrier ends in `.`, `!`, or `?`, subject to the address
finish-token limit. Finish tokens do not update arithmetic state and carry no
payload.

The receiver identifies the data boundary from the recovered stream length and
requires every remaining token to equal the deterministic candidate zero for
its exact context.

## 11. Line endings and carrier transport

LF is a normal visible character and can encode information like any other
eligible token. Multiple paragraphs are valid.

Before primer extraction and tokenization, a received carrier is canonicalized:

```text
CRLF -> LF
CR   -> LF
```

NUL is rejected. A single terminal file/text-area line ending may be removed by
the CLI because generated carriers always finish with sentence punctuation.
Other whitespace is preserved exactly.

Arbitrary whitespace folding, Unicode normalization, quote insertion, or prose
editing is not repaired and can make the carrier undecodable.

## 12. Decoding

The receiver:

1. canonicalizes line endings;
2. extracts and validates the first-sentence primer;
3. renders the exact prompt from address, subject, and primer;
4. tokenizes the complete carrier;
5. recomputes the candidate table at each continuation token;
6. feeds each observed candidate index to the arithmetic encoder;
7. derives and parses the masked stream length after the first 32 bytes;
8. validates the virtual suffix and greedy finish tokens;
9. unmasks and validates the outer payload;
10. authenticates HPKE with the visible context;
11. decompresses and validates the inner frame.

Any mismatch fails closed.

## 13. Capacity metrics

Implementations report:

```text
K_all = visible Unicode code points / stream bytes
```

Visible text includes primer, arithmetic data, LF paragraph separators, and
finish tokens. Useful companion metrics are UTF-8 carrier bytes per stream byte,
confirmed bits per arithmetic token, characters per token, and generation time.

## 14. Current qualification state

The pure codec, crypto, context binding, canonical line endings, and fake-model
round trips are automated. The pinned MLX profile passes its deterministic
self-test.

No real carrier fixture currently represents this exact protocol. The deleted
fixture used a different candidate filter and an obsolete arithmetic skip rule.
The next qualification step is a complete real-model round trip after candidate
construction is made fast enough to inspect long low-entropy trajectories.
