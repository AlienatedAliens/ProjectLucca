"""
Brain-agnostic runtime invariant (bake-off 2026-09-21).

Nothing under src/ may hard-code which LLM / server binary / chat template Lucca
runs. All of it derives from LLMSettings; volatile runtime facts reach the model
via the SELF epistemic substrate, not the system prompt.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lucca.brain.llm_client import build_chat_template_kwargs
from lucca.brain.prompt_builder import ARCHITECTURAL_SELF_AWARENESS
from lucca.brain.server_ctl import (
    build_launch_command,
    resolve_server_bin,
    resolve_template_file,
)
from lucca.core.config import LLMSettings

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "lucca"

# Vendor / model identifiers that must never appear as literals in runtime code.
# config.py is exempt only for its *default* field values (checked separately).
FORBIDDEN_LITERALS = (
    "Mistral NeMo",
    "Mistral-Nemo",
    "NeMo 12B",
    "gemma-4",
    "Gemma 4",
    "Bonsai",
    "Qwen3",
    "mistral-v3-tekken",
    "mistral_nemo.jinja",
)


# --------------------------------------------------------------------------- config


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (
            "llm/Mistral-Nemo-Instruct-2407-abliterated.Q6_K.gguf",
            "Mistral Nemo Instruct 2407 abliterated (Q6_K)",
        ),
        ("C:/x/gemma-4-12b-heretic-Q6_K.gguf", "gemma 4 12b heretic (Q6_K)"),
        ("Ternary-Bonsai-2-27B-PQ2_0.gguf", "Ternary Bonsai 2 27B (PQ2_0)"),
        ("plain-model.gguf", "plain model"),
    ],
)
def test_model_display_name_derived_from_filename(model: str, expected: str) -> None:
    assert LLMSettings(model=model).model_display_name() == expected


def test_model_display_name_override() -> None:
    cfg = LLMSettings(model="whatever.gguf", display_name="Lucca Brain v2")
    assert cfg.model_display_name() == "Lucca Brain v2"


def test_blank_optional_strings_become_none() -> None:
    cfg = LLMSettings(chat_template_file="", chat_template="   ", display_name="")
    assert cfg.chat_template_file is None
    assert cfg.chat_template is None
    assert cfg.display_name is None


def test_enable_thinking_defaults_false_for_companion_latency() -> None:
    assert LLMSettings().enable_thinking is False


# ------------------------------------------------------------------------ server_ctl


def _home_with_server(tmp_path: Path, rel_bin: str = "app/llama-server/llama-server.exe") -> Path:
    exe = tmp_path / rel_bin
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    return tmp_path


def test_launch_command_gemma_uses_embedded_template(tmp_path: Path) -> None:
    home = _home_with_server(tmp_path)
    cfg = LLMSettings(model="llm/gemma-4-12b-heretic-Q6_K.gguf", chat_template_file=None)
    cmd = build_launch_command(cfg, home)
    assert "--chat-template-file" not in cmd
    assert "--chat-template" not in cmd
    assert "--jinja" in cmd
    assert cmd[0] == str(home / "app" / "llama-server" / "llama-server.exe")


def test_launch_command_template_file_from_config(tmp_path: Path) -> None:
    home = _home_with_server(tmp_path)
    tpl = home / "templates" / "custom.jinja"
    tpl.parent.mkdir(parents=True)
    tpl.write_text("{{ messages }}", encoding="utf-8")
    cfg = LLMSettings(model="llm/anything.gguf", chat_template_file="templates/custom.jinja")
    cmd = build_launch_command(cfg, home)
    i = cmd.index("--chat-template-file")
    assert Path(cmd[i + 1]) == tpl


def test_launch_command_named_template_fallback(tmp_path: Path) -> None:
    home = _home_with_server(tmp_path)
    cfg = LLMSettings(
        model="llm/anything.gguf",
        chat_template_file="templates/does-not-exist.jinja",
        chat_template="chatml",
    )
    cmd = build_launch_command(cfg, home)
    assert "--chat-template-file" not in cmd
    assert cmd[cmd.index("--chat-template") + 1] == "chatml"


def test_server_bin_from_config_relative_and_absolute(tmp_path: Path) -> None:
    home = _home_with_server(tmp_path, "app/llama-server-prism/llama-server.exe")
    rel = LLMSettings(server_bin="app/llama-server-prism/llama-server.exe")
    assert resolve_server_bin(rel, home) == home / "app" / "llama-server-prism" / "llama-server.exe"
    abs_path = tmp_path / "elsewhere" / "srv.exe"
    absolute = LLMSettings(server_bin=str(abs_path))
    assert resolve_server_bin(absolute, home) == abs_path


def test_resolve_template_file_none_when_unset(tmp_path: Path) -> None:
    assert resolve_template_file(LLMSettings(chat_template_file=None), tmp_path) is None


def test_launch_command_has_no_model_name_sniffing(tmp_path: Path) -> None:
    """Two different model names with identical config must yield identical flags."""
    home = _home_with_server(tmp_path)
    a = build_launch_command(
        LLMSettings(model="llm/Mistral-Nemo-x.gguf", chat_template_file=None), home
    )
    b = build_launch_command(LLMSettings(model="llm/gemma-4-x.gguf", chat_template_file=None), home)

    def strip(cmd: list[str]) -> list[str]:
        return [x for x in cmd if not x.endswith(".gguf")]

    assert strip(a) == strip(b)


# ------------------------------------------------------------------------ llm_client


def test_chat_template_kwargs_forward_thinking_flag() -> None:
    assert build_chat_template_kwargs(LLMSettings(enable_thinking=False)) == {
        "tools_in_user_message": False,
        "enable_thinking": False,
    }
    assert build_chat_template_kwargs(LLMSettings(enable_thinking=True))["enable_thinking"] is True
    assert "enable_thinking" not in build_chat_template_kwargs(LLMSettings(enable_thinking=None))


# ------------------------------------------------------------------------ prompt


def test_system_prompt_invariants_contain_no_model_names() -> None:
    low = ARCHITECTURAL_SELF_AWARENESS.lower()
    for lit in ("mistral nemo", "gemma", "bonsai", "qwen", "kokoro-82m", "faster-whisper", "q6_k"):
        assert lit not in low, f"volatile runtime fact '{lit}' leaked into the system prompt"
    # Vendor denial must be generic, not single-vendor.
    assert "mistral ai, google, alibaba, meta" in low


# ------------------------------------------------------------------------ static gate


def test_no_hard_coded_brain_identifiers_in_src() -> None:
    """
    Static gate: forbid model/vendor literals in runtime code. LLMSettings default
    values in config.py are the single permitted location.
    """
    offenders: list[str] = []
    for py in SRC_ROOT.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="replace")
        if py.name == "config.py":
            # Only default field values may name a model; strip them before scanning.
            text = re.sub(
                r"^\s*(model|text_model|mmproj|chat_template_file):\s*str.*$", "", text, flags=re.M
            )
        for lit in FORBIDDEN_LITERALS:
            if lit.lower() in text.lower():
                offenders.append(f"{py.relative_to(SRC_ROOT)} :: {lit}")
    # UI download catalogue + settings copy are user-facing text, not runtime selection.
    offenders = [o for o in offenders if not o.startswith("ui\\") and not o.startswith("ui/")]
    assert not offenders, "hard-coded brain identifiers in runtime code:\n  " + "\n  ".join(
        offenders
    )
