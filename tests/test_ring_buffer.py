"""
Tests for SharedAudioRing (Spec 01 §5, Spec 07 §2, Property Test P-07)
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lucca.senses.ring_buffer import (
    FLAG_ABORT,
    FLAG_EOS,
    SharedAudioRing,
)

TEST_RING_NAME = "lucca_test_ring_p07"


@pytest.fixture
def ring():
    # 2 seconds at 16000 Hz = 32000 samples
    r = SharedAudioRing(name=TEST_RING_NAME, rate=16000, capacity_seconds=2, create=True)
    yield r
    r.close()
    r.unlink()


def test_ring_creation_and_header(ring):
    assert ring.rate == 16000
    assert ring.capacity_samples == 32000
    assert ring.write_idx == 0
    assert ring.read_idx == 0
    assert ring.available_read == 0
    assert ring.available_write == 32000


def test_basic_write_and_read(ring):
    data = np.arange(100, dtype=np.int16)
    written = ring.write(data)
    assert written == 100
    assert ring.available_read == 100

    read_data = ring.read(100)
    assert len(read_data) == 100
    np.testing.assert_array_equal(read_data, data)
    assert ring.available_read == 0


def test_read_partial_and_silence_fill(ring):
    data = np.array([10, 20, 30], dtype=np.int16)
    ring.write(data)

    # Request 5 samples, only 3 available -> 2 should be filled with zeros
    read_data = ring.read(5)
    assert len(read_data) == 5
    np.testing.assert_array_equal(read_data[:3], data)
    np.testing.assert_array_equal(read_data[3:], [0, 0])


def test_circular_wrap_around(ring):
    # Capacity is 32000. Write 30000, read 30000
    d1 = np.ones(30000, dtype=np.int16) * 5
    ring.write(d1)
    r1 = ring.read(30000)
    np.testing.assert_array_equal(r1, d1)

    # Now write 10000 samples which crosses the 32000 boundary (30000 + 10000 = 40000)
    d2 = np.arange(10000, dtype=np.int16)
    ring.write(d2)
    assert ring.available_read == 10000

    r2 = ring.read(10000)
    np.testing.assert_array_equal(r2, d2)


def test_read_slice(ring):
    data = np.arange(1000, dtype=np.int16) + 100
    ring.write(data)

    # Slice [200:500)
    s = ring.read_slice(200, 500)
    assert len(s) == 300
    np.testing.assert_array_equal(s, data[200:500])


def test_abort_flag_clears_ring(ring):
    data = np.arange(500, dtype=np.int16)
    ring.write(data)
    assert ring.available_read == 500

    ring.set_flag(FLAG_ABORT)
    assert ring.has_flag(FLAG_ABORT)

    # Read should drain immediately and return zeros
    out = ring.read(100)
    np.testing.assert_array_equal(out, np.zeros(100, dtype=np.int16))
    assert ring.available_read == 0


def test_eos_flag(ring):
    assert not ring.has_flag(FLAG_EOS)
    ring.set_flag(FLAG_EOS)
    assert ring.has_flag(FLAG_EOS)
    ring.clear_flag(FLAG_EOS)
    assert not ring.has_flag(FLAG_EOS)


# Hypothesis Property Test P-07: interleaved writes and reads preserve order
@settings(max_examples=100, deadline=None)
@given(
    chunks=st.lists(
        st.integers(min_value=1, max_value=2000),
        min_size=2,
        max_size=20,
    )
)
def test_hypothesis_interleaved_writes_reads(chunks):
    test_name = f"lucca_shm_prop_{abs(hash(tuple(chunks))) % 100000}"
    ring = SharedAudioRing(name=test_name, rate=16000, capacity_seconds=5, create=True)
    try:
        total_samples = sum(chunks)
        all_data = np.arange(total_samples, dtype=np.int16)

        read_collector = []
        offset = 0

        for chunk_size in chunks:
            chunk_data = all_data[offset : offset + chunk_size]
            ring.write(chunk_data)
            offset += chunk_size

            # Read half of what is available
            to_read = ring.available_read // 2
            if to_read > 0:
                got = ring.read(to_read)
                read_collector.append(got)

        # Drain remainder
        remaining = ring.available_read
        if remaining > 0:
            got = ring.read(remaining)
            read_collector.append(got)

        reconstructed = np.concatenate(read_collector)
        np.testing.assert_array_equal(reconstructed, all_data)
    finally:
        ring.close()
        ring.unlink()
