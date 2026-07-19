# Interoperability status

Stages 0 and 1 are implemented for Python 3.12 with `cryptography==49.0.0`.
Binary exchange uses the exact inner, HPKE, outer payload, and stego framing from
the protocol. The HPKE suite is checked against RFC 9180 Appendix A.1 inputs;
because the selected single-shot API has no AAD parameter, the fixture uses the
published sequence-0 key and nonce with empty AAD. No model/runtime profile is
qualified yet, and the example JSON is therefore a structural Stage 1 template
rather than a publishable generative address.

The next stage must add stable binary fixtures and the fake-model arithmetic
codec before any real-model interoperability claim.
