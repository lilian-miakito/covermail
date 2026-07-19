"""MSB-first framed bit sources and collectors."""

from __future__ import annotations


class FramedBitSource:
    """Real bytes followed by the v1 infinite alternating 1,0 suffix."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    @property
    def real_bits(self) -> int:
        return len(self.data) * 8

    def bit(self, offset: int) -> int:
        if offset < 0:
            raise ValueError("negative bit offset")
        if offset < self.real_bits:
            byte = self.data[offset // 8]
            return (byte >> (7 - offset % 8)) & 1
        return 1 if (offset - self.real_bits) % 2 == 0 else 0


class BitCollector:
    """Collect bits MSB-first while retaining partial final bytes."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.count = 0

    def append(self, bit: int) -> None:
        if bit not in (0, 1):
            raise ValueError("bit must be zero or one")
        if self.count % 8 == 0:
            self.data.append(0)
        if bit:
            self.data[self.count // 8] |= 1 << (7 - self.count % 8)
        self.count += 1

    def bit(self, offset: int) -> int:
        if not 0 <= offset < self.count:
            raise IndexError("bit offset outside collector")
        return (self.data[offset // 8] >> (7 - offset % 8)) & 1

    def complete_bytes(self) -> bytes:
        return bytes(self.data[: self.count // 8])
