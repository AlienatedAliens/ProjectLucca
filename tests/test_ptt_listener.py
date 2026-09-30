"""
Project Lucca — Unit Tests for Push-to-Talk (PTT) Key Mapping & Resolution
Spec 07 §1, WO-18e
"""

from __future__ import annotations

from lucca.senses.ptt import (
    VK_CONTROL,
    VK_LCONTROL,
    VK_LMENU,
    VK_LSHIFT,
    VK_MENU,
    VK_RCONTROL,
    VK_RMENU,
    VK_RSHIFT,
    VK_SHIFT,
    VK_SPACE,
    PTTListener,
    resolve_key_codes,
)


def test_resolve_key_codes_alt_gr() -> None:
    """Alt-Gr in any alias format must resolve to VK_RMENU only (no generic VK_MENU)."""
    aliases = ["alt_gr", "alt-gr", "alt gr", "altgr", "Alt-Gr", "ALT_GR", "right_alt", "ralt"]
    for alias in aliases:
        codes = resolve_key_codes(alias)
        assert codes == [VK_RMENU], f"Failed for alias: {alias}"
        # Critical: Must not contain VK_MENU (0x12) which triggers on Left-Alt
        assert VK_MENU not in codes
        assert VK_LMENU not in codes
        assert VK_SHIFT not in codes


def test_resolve_key_codes_modifiers() -> None:
    """Right and Left modifiers must be distinctly mapped."""
    assert resolve_key_codes("right_ctrl") == [VK_RCONTROL]
    assert resolve_key_codes("ctrl_r") == [VK_RCONTROL]
    assert VK_CONTROL not in resolve_key_codes("right_ctrl")
    assert VK_LCONTROL not in resolve_key_codes("right_ctrl")

    assert resolve_key_codes("left_ctrl") == [VK_LCONTROL]
    assert resolve_key_codes("right_shift") == [VK_RSHIFT]
    assert VK_SHIFT not in resolve_key_codes("right_shift")
    assert resolve_key_codes("left_shift") == [VK_LSHIFT]
    assert resolve_key_codes("space") == [VK_SPACE]


def test_resolve_key_codes_universal_any() -> None:
    """Universal Any must only trigger on right-hand modifiers, never generic or left keys."""
    codes = resolve_key_codes("any")
    assert codes == [VK_RMENU, VK_RCONTROL, VK_RSHIFT]
    assert VK_MENU not in codes
    assert VK_LMENU not in codes
    assert VK_CONTROL not in codes
    assert VK_LCONTROL not in codes
    assert VK_SHIFT not in codes
    assert VK_LSHIFT not in codes


def test_ptt_listener_dynamic_rebind() -> None:
    """PTTListener.set_key() must dynamically update target_vks for all supported keys."""
    listener = PTTListener(
        on_pressed=lambda _ts: None,
        on_released=lambda _ts, _dur: None,
        key_name="alt_gr",
    )
    assert listener.target_vks == [VK_RMENU]

    listener.set_key("right_ctrl")
    assert listener.target_vks == [VK_RCONTROL]

    listener.set_key("space")
    assert listener.target_vks == [VK_SPACE]

    listener.set_key("alt-gr")
    assert listener.target_vks == [VK_RMENU]

    listener.set_key("any")
    assert listener.target_vks == [VK_RMENU, VK_RCONTROL, VK_RSHIFT]
