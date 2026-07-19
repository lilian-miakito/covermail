# Interoperability status

The pure protocol and fake-model layers round-trip arbitrary practical payloads
through the 32-bit inverse arithmetic coder without special low-entropy states.
The complete automated suite also covers HPKE, context binding, masking,
termination, tokenizer round trips, LF carrier text, and CLI orchestration.

The single MLX profile passes its deterministic model self-test on the local
qualified host. Its exact artifacts and runtime are pinned in the public
address fixture.

The committed real-model fixture completes an encode/decode/HPKE round trip for
the active codec on the local qualification host. It contains ten LF characters
and recovers all 114 stream bytes exactly. `K_all` is 12.3947 characters per
stream byte; reference times are 132.13 s encode and 129.62 s decode.

Before claiming interoperability:

1. optimize candidate construction without changing the exact final tables;
2. profile and improve carrier quality without altering arithmetic recovery;
3. exchange independently generated carriers between two clean compatible
   installations;
4. compare decoded bytes and plaintext bit-for-bit.
