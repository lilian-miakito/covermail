"""Typed, non-secret-bearing errors for the Covermail protocol."""


class CovermailError(Exception):
    """Base class for expected Covermail failures."""


class AddressParseError(CovermailError):
    """The public address is not strict Covermail JSON."""


class AddressValidationError(CovermailError):
    """The public address does not satisfy the v1 schema."""


class InnerFrameError(CovermailError):
    """The authenticated inner plaintext frame is malformed."""


class OuterFrameError(CovermailError):
    """The recovered outer frame is malformed."""


class WrongAddressError(OuterFrameError):
    """The outer frame is not for the selected address."""


class PrivateKeyLockedError(CovermailError):
    """The encrypted private key could not be unlocked."""


class IdentityStorageError(CovermailError):
    """A private identity could not be safely stored or loaded."""


class DecryptionError(CovermailError):
    """HPKE authentication failed for an intentionally unspecified reason."""


class CarrierGenerationError(CovermailError):
    """A carrier could not be generated within protocol limits."""


class CarrierStructureError(CovermailError):
    """A carrier violates the visible one-paragraph profile."""


class CarrierTokenizationError(CovermailError):
    """Carrier text does not reproduce its token sequence exactly."""


class CarrierArithmeticError(CovermailError):
    """The carrier arithmetic stream is malformed or incomplete."""
