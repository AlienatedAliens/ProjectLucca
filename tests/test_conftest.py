import tempfile
from pathlib import Path

from lucca.core.config import get_config


def test_tests_run_in_tmp_home() -> None:
    """Verifies that tests run with LUCCA_HOME isolated to a temporary directory."""
    home = get_config().home_dir
    temp_dir = Path(tempfile.gettempdir()).resolve()
    assert home != Path("C:/ProjectLucca").resolve()
    try:
        home.relative_to(temp_dir)
        is_temp = True
    except ValueError:
        is_temp = "temp" in str(home).lower() or "tmp" in str(home).lower()
    assert is_temp, f"Expected {home} to be inside temporary directory, but it was not."
