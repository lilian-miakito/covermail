# Interoperability status

Stages 0 through 2 are implemented for Python 3.12 with `cryptography==49.0.0`.
Binary exchange uses the exact inner, HPKE, outer payload, and stego framing from
the protocol. The HPKE suite is checked against RFC 9180 Appendix A.1 inputs;
because the selected single-shot API has no AAD parameter, the fixture uses the
published sequence-0 key and nonce with empty AAD. No model/runtime profile is
qualified yet. The deterministic fake model round-trips arbitrary practical
payloads through the v1 32-bit arithmetic coder and has a stored carrier fixture.
The example JSON remains a structural template rather than a publishable
generative address.

The next stage must qualify a real model/runtime profile, implement prompt and
candidate construction against that backend, and produce cross-installation
fixtures before any real-model interoperability claim.
