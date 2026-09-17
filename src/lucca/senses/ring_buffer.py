"""
Project Lucca — Shared Memory Audio Ring Buffer
Spec 01 §5, Spec 07 §2, ADR-008
"""

import struct
from multiprocessing import shared_memory
from typing import Final

import numpy as np
import numpy.typing as npt

# Header layout (64 bytes):
# magic (u32: 0x4C554341, "LUCA")
# version (u16: 1)
# rate (u32: e.g. 16000 or 24000)
# write_idx (u64: monotonic total samples written)
# read_idx (u64: monotonic total samples read)
# seq (u64: monotonic sequence identifier)
# flags (u32: bitmask: 1=ABORT, 2=EOS)
# pad (26 bytes reserved)
HEADER_FORMAT: Final[str] = ">IHIQQQI26x"
HEADER_SIZE: Final[int] = 64
MAGIC: Final[int] = 0x4C554341
VERSION: Final[int] = 1

FLAG_ABORT: Final[int] = 1
FLAG_EOS: Final[int] = 2

CAP_RING_NAME: Final[str] = "lucca_cap_ring"
CAP_RING_RATE: Final[int] = 16000
CAP_RING_SEC: Final[int] = 60

PLAY_RING_NAME: Final[str] = "lucca_play_ring"
PLAY_RING_RATE: Final[int] = 24000
PLAY_RING_SEC: Final[int] = 30


class SharedAudioRing:
    """
    Lock-free shared-memory ring buffer for PCM audio streaming.
    Backing memory: Windows Named Shared Memory (multiprocessing.shared_memory).
    """

    buf: memoryview

    def __init__(
        self,
        name: str,
        rate: int,
        capacity_seconds: int,
        create: bool = False,
    ) -> None:
        self.name = name
        self.rate = rate
        self.capacity_samples = rate * capacity_seconds
        self.sample_bytes = 2  # int16
        self.data_size = self.capacity_samples * self.sample_bytes
        self.total_size = HEADER_SIZE + self.data_size

        if create:
            try:
                self.shm = shared_memory.SharedMemory(
                    name=self.name, create=True, size=self.total_size
                )
            except FileExistsError:
                # Attach to existing and reset
                self.shm = shared_memory.SharedMemory(name=self.name)
            buf = self.shm.buf
            if buf is None:
                raise RuntimeError(f"SharedMemory '{self.name}' has unallocated buffer")
            self.buf = buf
            self._write_header(write_idx=0, read_idx=0, seq=0, flags=0)
        else:
            self.shm = shared_memory.SharedMemory(name=self.name)
            buf = self.shm.buf
            if buf is None:
                raise RuntimeError(f"SharedMemory '{self.name}' has unallocated buffer")
            self.buf = buf

    def _write_header(self, write_idx: int, read_idx: int, seq: int, flags: int) -> None:
        struct.pack_into(
            HEADER_FORMAT,
            self.buf,
            0,
            MAGIC,
            VERSION,
            self.rate,
            write_idx,
            read_idx,
            seq,
            flags,
        )

    def _read_header(self) -> tuple[int, int, int, int, int, int, int]:
        magic, ver, rate, w_idx, r_idx, seq, flags = struct.unpack_from(
            HEADER_FORMAT, self.buf, 0
        )
        if magic != MAGIC:
            raise ValueError(f"Invalid shared memory magic: {hex(magic)}")
        return magic, ver, rate, w_idx, r_idx, seq, flags

    @property
    def write_idx(self) -> int:
        return self._read_header()[3]

    @property
    def read_idx(self) -> int:
        return self._read_header()[4]

    @property
    def flags(self) -> int:
        return self._read_header()[6]

    @property
    def available_read(self) -> int:
        _, _, _, w, r, _, _ = self._read_header()
        return max(0, w - r)

    @property
    def available_write(self) -> int:
        _, _, _, w, r, _, _ = self._read_header()
        return max(0, self.capacity_samples - (w - r))

    def set_flag(self, flag: int) -> None:
        _, _, _, w, r, seq, f = self._read_header()
        self._write_header(w, r, seq, f | flag)

    def clear_flag(self, flag: int) -> None:
        _, _, _, w, r, seq, f = self._read_header()
        self._write_header(w, r, seq, f & ~flag)

    def has_flag(self, flag: int) -> bool:
        return (self.flags & flag) == flag

    def reset(self) -> None:
        """Resets the ring buffer pointers and flags."""
        self._write_header(write_idx=0, read_idx=0, seq=0, flags=0)

    def write(self, samples: npt.NDArray[np.int16] | bytes) -> int:
        """
        Writes int16 audio samples into the ring buffer.
        Returns number of samples written.
        """
        if isinstance(samples, np.ndarray):
            if samples.dtype != np.int16:
                samples = samples.astype(np.int16)
            raw_bytes = samples.tobytes()
            n_samples = len(samples)
        else:
            raw_bytes = samples
            n_samples = len(raw_bytes) // 2

        if n_samples == 0:
            return 0

        _, _, _, w_idx, r_idx, seq, flags = self._read_header()

        # Handle overflow if write exceeds capacity: advance read pointer
        if (w_idx - r_idx) + n_samples > self.capacity_samples:
            r_idx = w_idx + n_samples - self.capacity_samples

        # Write data handling circular wrap-around
        start_sample = w_idx % self.capacity_samples
        first_part_samples = min(n_samples, self.capacity_samples - start_sample)
        second_part_samples = n_samples - first_part_samples

        first_byte_start = HEADER_SIZE + (start_sample * 2)
        first_byte_end = first_byte_start + (first_part_samples * 2)
        self.buf[first_byte_start:first_byte_end] = raw_bytes[: first_part_samples * 2]

        if second_part_samples > 0:
            second_byte_start = HEADER_SIZE
            second_byte_end = HEADER_SIZE + (second_part_samples * 2)
            self.buf[second_byte_start:second_byte_end] = raw_bytes[first_part_samples * 2 :]

        # Update write_idx in header (release semantics)
        self._write_header(w_idx + n_samples, r_idx, seq, flags)
        return n_samples

    def read(self, n_samples: int) -> npt.NDArray[np.int16]:
        """
        Non-blocking read for audio callback.
        Reads up to n_samples; fills remainder with zeros (silence).
        Always returns an array of length exactly n_samples (dtype=int16).
        """
        result = np.zeros(n_samples, dtype=np.int16)
        _, _, _, w_idx, r_idx, seq, flags = self._read_header()

        # Check for abort flag
        if flags & FLAG_ABORT:
            # Drain immediately
            self._write_header(w_idx, w_idx, seq, flags)
            return result

        avail = max(0, w_idx - r_idx)
        to_read = min(n_samples, avail)
        if to_read == 0:
            return result

        start_sample = r_idx % self.capacity_samples
        first_part_samples = min(to_read, self.capacity_samples - start_sample)
        second_part_samples = to_read - first_part_samples

        first_byte_start = HEADER_SIZE + (start_sample * 2)
        first_byte_end = first_byte_start + (first_part_samples * 2)
        part1 = np.frombuffer(self.buf[first_byte_start:first_byte_end], dtype=np.int16)
        result[:first_part_samples] = part1

        if second_part_samples > 0:
            second_byte_start = HEADER_SIZE
            second_byte_end = HEADER_SIZE + (second_part_samples * 2)
            part2 = np.frombuffer(self.buf[second_byte_start:second_byte_end], dtype=np.int16)
            result[first_part_samples:to_read] = part2

        # Advance read pointer
        self._write_header(w_idx, r_idx + to_read, seq, flags)
        return result

    def read_slice(self, start_seq: int, end_seq: int) -> npt.NDArray[np.int16]:
        """
        Reads an absolute sample slice [start_seq, end_seq) from the ring.
        Used by ASR to transcribe specific PTT windows without advancing read_idx.
        """
        if end_seq <= start_seq:
            return np.zeros(0, dtype=np.int16)

        n_samples = end_seq - start_seq
        result = np.zeros(n_samples, dtype=np.int16)

        start_pos = start_seq % self.capacity_samples
        first_part_samples = min(n_samples, self.capacity_samples - start_pos)
        second_part_samples = n_samples - first_part_samples

        b_start1 = HEADER_SIZE + (start_pos * 2)
        b_end1 = b_start1 + (first_part_samples * 2)
        result[:first_part_samples] = np.frombuffer(self.buf[b_start1:b_end1], dtype=np.int16)

        if second_part_samples > 0:
            b_start2 = HEADER_SIZE
            b_end2 = HEADER_SIZE + (second_part_samples * 2)
            result[first_part_samples:] = np.frombuffer(self.buf[b_start2:b_end2], dtype=np.int16)

        return result

    def close(self) -> None:
        self.shm.close()

    def unlink(self) -> None:
        try:
            self.shm.unlink()
        except FileNotFoundError:
            pass


def get_capture_ring(create: bool = False) -> SharedAudioRing:
    return SharedAudioRing(
        name=CAP_RING_NAME,
        rate=CAP_RING_RATE,
        capacity_seconds=CAP_RING_SEC,
        create=create,
    )


def get_playback_ring(create: bool = False) -> SharedAudioRing:
    return SharedAudioRing(
        name=PLAY_RING_NAME,
        rate=PLAY_RING_RATE,
        capacity_seconds=PLAY_RING_SEC,
        create=create,
    )
