"""Canonical unsigned LEB128 lengths."""


def encode_uvarint(value: int) -> bytes:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("uvarint value must be an integer")
    if value < 0:
        raise ValueError("negative uvarint")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def decode_uvarint(data: bytes, offset: int = 0, *, max_bytes: int = 5) -> tuple[int, int]:
    if offset < 0 or offset > len(data):
        raise ValueError("uvarint offset outside input")
    if max_bytes < 1:
        raise ValueError("uvarint max_bytes must be positive")
    value = 0
    shift = 0
    for index in range(max_bytes):
        position = offset + index
        if position >= len(data):
            raise EOFError("incomplete uvarint")
        byte = data[position]
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            consumed = index + 1
            if data[offset : offset + consumed] != encode_uvarint(value):
                raise ValueError("non-canonical uvarint")
            return value, consumed
        shift += 7
    raise ValueError("uvarint exceeds limit")
