from collections.abc import Iterator
from pathlib import Path

import pytest

from lucca.core.config import get_config


@pytest.fixture(autouse=True)
def _isolated_lucca_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    home = tmp_path / "lucca_home"
    home.mkdir(parents=True, exist_ok=True)
    for sub in ("models", "data", "workspace", "inbox", "logs", "cache", "tmp"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LUCCA_HOME", str(home))
    get_config.cache_clear()
    yield home
    get_config.cache_clear()


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
