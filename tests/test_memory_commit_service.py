"""
WO-37 Phase 3 — Memory Commit Service & Belief Stance Topic Extraction Tests
Spec §7, WP-2, Gate G-WO37-BELIEF-TOPIC
"""

from __future__ import annotations

import pytest

from lucca.core.memory_commit_service import _extract_stance_topic


def test_stance_topic_extraction_stopword_filter() -> None:
    """WO-37 Phase 3 Gate (G-WO37-BELIEF-TOPIC):
    Verifies that idiomatic phrases with stopwords/pronouns do not extract garbage topics like 'about it'.
    """
    # Key bug report case: idiom at the end of utterance should fall back to pre-marker clause
    t1 = "My engagement register is quite high when I think about it"
    res1 = _extract_stance_topic(t1)
    assert res1 != "about it"
    assert res1 == "My engagement register is quite high"

    # Stopword-only candidate followed by non-stopword ("a lot")
    t2 = "I think about it a lot"
    res2 = _extract_stance_topic(t2)
    assert res2 != "about it"
    assert "a lot" in res2 or "about it a lot" in res2

    # Existing behavior preserved: clear post-marker stance clause
    t3 = "I believe that neural scaling is the key insight here"
    res3 = _extract_stance_topic(t3)
    assert res3 == "that neural scaling is the key insight"

    # Post-marker with "in my view"
    t4 = "In my view, local models are superior for privacy"
    res4 = _extract_stance_topic(t4)
    assert res4 == "local models are superior for privacy"

    # Idiom where post-marker is only "so" or "that"
    t5 = "The speed is sufficient if I think so"
    res5 = _extract_stance_topic(t5)
    assert res5 != "so"
    assert res5 == "The speed is sufficient"
