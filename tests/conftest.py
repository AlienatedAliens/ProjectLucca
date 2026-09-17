"""
Project Lucca — Pytest Configuration & Common Fixtures
Spec 10 (Testing Matrix v2)
"""

import pytest


@pytest.fixture
def sample_state():
    from lucca.core.schemas import RuleState

    return RuleState(
        schema_version=1,
        transcript="open calculator",
        transcript_lower="open calculator",
        intent="launch_app",
        intent_conf=0.95,
        entities={"app": ["calculator"]},
        apps_running=frozenset(),
    )
