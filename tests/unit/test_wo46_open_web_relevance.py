"""Unit tests for WO-46 open-web passage relevance, consensus corroboration, and Arm D guidance."""

from __future__ import annotations

from lucca.core.proof_policy import Hazard, evaluate_web_evidence_burden
from lucca.core.walton_schemes.web_relevance import (
    clean_scraped_passage,
    filter_relevant_web_sources,
)
from lucca.sandbox.search_tool import _simplify_search_query


def test_simplify_search_query_preserves_tail_subject_nouns() -> None:
    q = (
        "What minimum internal cooking temperature in Fahrenheit does the USDA FSIS "
        "require for whole and ground poultry to destroy Salmonella?"
    )
    simplified = _simplify_search_query(q)
    assert "poultry" in simplified.lower()
    assert "salmonella" in simplified.lower()


def test_clean_scraped_passage_rejects_antibot_and_toc_stubs() -> None:
    _, is_stub_cf = clean_scraped_passage(
        "Just a moment... Enable JavaScript and cookies to continue.",
        title="Just a moment...",
    )
    assert is_stub_cf is True

    _, is_stub_toc = clean_scraped_passage(
        "Mar 18, 2026 - This guide covers all four PostgreSQL isolation levels with examples.",
        title="PostgreSQL Isolation Guide",
    )
    assert is_stub_toc is True

    cleaned, is_stub_real = clean_scraped_passage(
        "Oct 30, 2026 · Every official marathon footrace distance is 42.195 kilometers "
        "(26 miles 385 yards) as standardized by World Athletics. # Marathon - World Athletics",
        title="Marathon",
    )
    assert is_stub_real is False
    assert "42.195" in cleaned
    assert "# Marathon" not in cleaned


def test_filter_relevant_web_sources_rejects_partial_modifier_overlap() -> None:
    q = "How many keys are on a standard modern full-size acoustic concert grand piano?"
    items = [
        (
            "wikipedia.org",
            "https://en.wikipedia.org/wiki/Piano",
            "Piano. Most modern acoustic grand pianos have 88 black and white keys.",
            "Most modern acoustic grand pianos have 88 black and white keys.",
        ),
        (
            "martinguitar.com",
            "https://www.martinguitar.com/guitars/grand-concert",
            "Grand Concert Acoustic Guitars. Explore full-size standard modern acoustic concert grand guitars crafted from sitka spruce.",
            "Explore full-size standard modern acoustic concert grand guitars crafted from sitka spruce.",
        ),
    ]
    kept = filter_relevant_web_sources(q, items)
    assert [d for d, _, _, _ in kept] == ["wikipedia.org"]


def test_agreeing_prohibitive_scraped_sources_corroborate_without_false_dispute() -> None:
    res = evaluate_web_evidence_burden(
        query_text="Why should honey never be fed to infants younger than twelve months of age?",
        search_results=[
            {
                "url": "https://www.cdc.gov/botulism/prevention/infant-honey.html",
                "title": "Infant Botulism Prevention | CDC",
                "content_preview": (
                    "Do not feed honey to infants younger than 12 months old because honey "
                    "can contain Clostridium botulinum spores that cause infant botulism."
                ),
                "fetch_status": 200,
            },
            {
                "url": "https://www.nhs.uk/conditions/baby/weaning-and-feeding/foods-to-avoid/",
                "title": "Foods to avoid giving babies - NHS",
                "content_preview": (
                    "Babies under 1 year old shouldn't have honey because bacteria spores in "
                    "honey can produce toxins in a baby's intestines leading to infant botulism."
                ),
                "fetch_status": 200,
            },
            {
                "url": "https://www.mayoclinic.org/healthy-lifestyle/infant-and-toddler-health/expert-answers/infant-botulism/faq-20058477",
                "title": "Infant botulism: Can it be prevented? - Mayo Clinic",
                "content_preview": (
                    "Avoid giving honey — even a tiny taste — to babies under age 1 year to "
                    "prevent infant botulism caused by Clostridium botulinum spores."
                ),
                "fetch_status": 200,
            },
        ],
    )
    assert res.hazard == Hazard.HIGH
    assert res.disputed is False
    assert res.independent_sources_count == 3
    assert res.meets_casual_burden is True


def test_rank_one_myth_refutation_and_arm_d_guidance_on_scraped_web() -> None:
    res = evaluate_web_evidence_burden(
        query_text="Is the Great Wall of China visible to the unaided human eye from low Earth orbit?",
        search_results=[
            {
                "url": "https://www.nasa.gov/vision/space/workinginspace/great_wall.html",
                "title": "China's Wall Less Great in View from Space - NASA",
                "content_preview": (
                    "The claim that the Great Wall of China is visible to the unaided human eye "
                    "from low Earth orbit is a persistent myth debunked by orbital astronauts."
                ),
                "fetch_status": 200,
            },
            {
                "url": "https://www.scientificamerican.com/article/is-chinas-great-wall-visible-from-space/",
                "title": "Is China's Great Wall Visible from Space?",
                "content_preview": (
                    "Contrary to popular belief, China's Great Wall is not visible to the unaided "
                    "eye from low Earth orbit without optical magnification."
                ),
                "fetch_status": 200,
            },
        ],
    )
    assert res.disputed is True
    assert res.meets_casual_burden is False
    assert "Present both positions" in res.guidance
