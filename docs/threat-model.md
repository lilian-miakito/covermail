# Threat model

The normative boundaries are stated in [section 1 of the protocol](protocol.md#1-purpose-and-boundaries).

Covermail protects the authenticated inner plaintext with RFC 9180 HPKE Base.
The single encrypted capsule binds the canonical public address, exact public
length header B and exact 64 visible A token IDs. B and C are encoded in
deterministic Qwen 3.5 token choices; the LLM is a steganographic transport,
not the cipher.

The sender-only writing brief, A sampling seed and local D finish policy are
not authenticated protocol inputs. D is deliberately ignored by the decoder
and may be edited or removed if the A/B/C tokenization remains unchanged.

The current system does not authenticate the sender, prevent replay, hide
transport metadata or approximate payload length, protect compromised
endpoints, solve public-address substitution, repair edited prose, or promise
resistance to model fingerprinting and trained steganalysis.

The Stage 4 web application adds a loopback security boundary, not a remote
service. It caps request bodies, disables access logs, and serves a CSP without
remote assets. The development application intentionally has no session,
Host, or Origin gate. Its network boundary is only the loopback bind. It does
not protect a compromised browser, operating system, user account, or process
with access to Covermail memory and identity files.
