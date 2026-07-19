# Threat model

The normative threat model is [section 4 of the protocol](protocol.md#4-threat-model).

Stage 1 protects the authenticated inner plaintext with RFC 9180 HPKE Base and
binds the full canonical public address in `info`. It does not authenticate the
sender, prevent replay, hide transport metadata, protect compromised endpoints,
or solve public-address substitution. The binary frame currently exposed by the
CLI is not camouflage; generative transport is intentionally deferred.
