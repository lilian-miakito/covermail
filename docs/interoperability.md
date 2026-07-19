# Interoperability status

The pure protocol and fake-model layers round-trip arbitrary practical payloads
through the 32-bit inverse arithmetic coder without special low-entropy states.
The complete automated suite also covers HPKE, context binding, masking,
termination, tokenizer round trips, LF carrier text, and CLI orchestration.

The single MLX profile passes its deterministic model self-test on the local
qualified host. Its exact artifacts and runtime are pinned in the public
address fixture.

There is currently no committed real-model carrier fixture for the active
codec. Historical carriers used a different codec and protocol labels, so
retaining them would falsely imply compatibility.

Before claiming interoperability:

1. optimize candidate construction without changing the exact final tables;
2. complete a real-model encode/decode round trip with the active codec;
3. record `K_all`, tokens, entropy/progress, runtime, and carrier quality;
4. exchange independently generated carriers between two clean compatible
   installations;
5. compare decoded bytes and plaintext bit-for-bit.
