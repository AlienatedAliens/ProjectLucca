"""
Unit tests for persona.toml lossless serialization
Spec 16 §3, WI-1, WI-6
"""

import tomllib
from pathlib import Path

from lucca.brain.prompt_builder import (
    get_persona_config,
    load_persona_from_config,
    save_persona_to_config,
)


def test_toml_serializer_preserves_comments_and_formatting(tmp_path: Path) -> None:
    """Verifies that line-level TOML updater preserves comments, tables, and formatting."""
    initial_toml = (
        "# Project Lucca — Persona Configuration File\n"
        "# Custom author comments that must never be stripped\n\n"
        'name = "Lucca"\n'
        'voice = "genki_heroine"\n'
        'archetype = "inventor"          # built-in default\n'
        'formality = "casual"            # "casual" | "neutral" | "precise"\n'
        'custom_prompt = """"""\n'
        "uses_your_name = true\n"
        'admits_uncertainty = true        # says "I\'m not sure"\n\n'
        "[boundaries]\n"
        "# Safety boundaries\n"
        "never_pretend_to_feel = true\n"
        'refuse_topics = ["medical_diagnosis", "financial_advice"]\n\n'
        "[affect]\n"
        "enabled = true\n"
        "decay_tau_seconds = 600.0       # 10 minute half-life\n"
        "max_speed_delta = 0.10          # ±10% TTS speed modulation\n"
    )

    toml_file = tmp_path / "persona.toml"
    toml_file.write_text(initial_toml, encoding="utf-8")

    # Update through save_persona_to_config
    save_persona_to_config(
        archetype="genki",
        formality="precise",
        custom_prompt="Keep statements brief and clear.",
        technical_depth=0.75,
        warmth=0.80,
        directness=0.90,
        uses_your_name=False,
        admits_uncertainty=True,
        never_pretend_to_feel=True,
        refuse_topics=["unauthorized execution", "medical diagnosis"],
        affect_enabled=True,
        decay_tau_seconds=300.0,
        max_speed_delta=0.15,
        config_path=toml_file,
    )

    saved_text = toml_file.read_text(encoding="utf-8")

    # 1. Assert comments were preserved
    assert "# Custom author comments that must never be stripped" in saved_text
    assert '# says "I\'m not sure"' in saved_text
    assert "# 10 minute half-life" in saved_text

    # 2. Assert updated values exist and parse with tomllib
    parsed = tomllib.loads(saved_text)
    assert parsed["archetype"] == "genki"
    assert parsed["formality"] == "precise"
    assert parsed["custom_prompt"] == "Keep statements brief and clear."
    assert parsed["uses_your_name"] is False
    assert parsed["admits_uncertainty"] is True

    # 3. Assert boundaries and refuse_topics list preserved as valid list
    assert parsed["boundaries"]["never_pretend_to_feel"] is True
    assert parsed["boundaries"]["refuse_topics"] == ["unauthorized execution", "medical diagnosis"]

    # 4. Assert affect settings preserved
    assert parsed["affect"]["enabled"] is True
    assert parsed["affect"]["decay_tau_seconds"] == 300.0
    assert parsed["affect"]["max_speed_delta"] == 0.15

    # 5. Assert traits table created/updated
    assert parsed["traits"]["technical_depth"] == 0.75
    assert parsed["traits"]["warmth"] == 0.80
    assert parsed["traits"]["directness"] == 0.90


def test_round_trip_load_save_load(tmp_path: Path) -> None:
    """Verifies complete round-trip: load -> modify -> save -> load yields identical state."""
    toml_file = tmp_path / "persona.toml"

    save_persona_to_config(
        archetype="kuudere",
        formality="neutral",
        custom_prompt="Precision over pleasantries.",
        technical_depth=0.85,
        warmth=0.20,
        directness=0.95,
        uses_your_name=True,
        admits_uncertainty=True,
        never_pretend_to_feel=True,
        refuse_topics=["speculation"],
        config_path=toml_file,
    )

    load_persona_from_config(config_path=toml_file)
    cfg1 = get_persona_config(config_path=toml_file)

    # Re-save identical values
    save_persona_to_config(
        archetype=cfg1["archetype"],
        formality=cfg1["formality"],
        custom_prompt=cfg1["custom_prompt"],
        technical_depth=cfg1["traits"]["technical_depth"],
        warmth=cfg1["traits"]["warmth"],
        directness=cfg1["traits"]["directness"],
        uses_your_name=cfg1["uses_your_name"],
        admits_uncertainty=cfg1["admits_uncertainty"],
        never_pretend_to_feel=cfg1["boundaries"]["never_pretend_to_feel"],
        refuse_topics=cfg1["boundaries"]["refuse_topics"],
        config_path=toml_file,
    )

    cfg2 = get_persona_config(config_path=toml_file)
    assert cfg1 == cfg2


def test_voice_speed_ptt_dsp_persistence(tmp_path: Path) -> None:
    """Verifies that voice, speed, ptt_key, and dsp settings persist and load cleanly."""
    toml_file = tmp_path / "persona.toml"

    save_persona_to_config(
        archetype="inventor",
        formality="casual",
        custom_prompt="Invent something great!",
        voice="blend:0.70*af_sky+0.30*jf_alpha",
        speed=1.20,
        ptt_key="ctrl_r",
        dsp_pitch_semitones=3.5,
        dsp_enabled=True,
        config_path=toml_file,
    )

    loaded = get_persona_config(config_path=toml_file)
    assert loaded.voice == "blend:0.70*af_sky+0.30*jf_alpha"
    assert loaded.speed == 1.20
    assert loaded.ptt_key == "ctrl_r"
    assert loaded.dsp_pitch_semitones == 3.5
    assert loaded.dsp_enabled is True
