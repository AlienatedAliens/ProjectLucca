"""
Unit tests for PyQt6 desktop companion widgets (SpeechBubble, QuickChatBar, CompanionSprite).
Runs headlessly under offscreen QPA platform.
"""

import os

import pytest
from PyQt6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from lucca.ui.input_bar import QuickChatBar
from lucca.ui.speech_bubble import SpeechBubble
from lucca.ui.sprite import CompanionSprite


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_speech_bubble_states(qapp):
    confirmed = []
    bubble = SpeechBubble(on_confirm=confirmed.append)

    # Caption test
    bubble.show_caption("Hello, traveler!", source="assistant", is_final=False)
    assert bubble.current_text == "Hello, traveler!"
    assert bubble.header_label.text() == "LUCCA"

    # Status test
    bubble.show_caption("Listening... 🎙️", source="status", is_final=False)
    assert bubble.header_label.text() == "STATUS"

    # User caption test
    bubble.show_caption("What is the time?", source="user", is_final=True)
    assert bubble.header_label.text() == "YOU"

    # Confirmation test
    bubble.show_confirmation("Launch notepad?", summary="launch_app notepad")
    assert bubble.confirm_widget.isVisible()
    bubble._handle_confirmation(True)
    assert confirmed == [True]


def test_quick_chat_bar(qapp):
    sent_messages = []
    bar = QuickChatBar(on_send_text=sent_messages.append)

    bar.input_field.setText("System check")
    bar._handle_submit()
    assert sent_messages == ["System check"]
    assert bar.input_field.text() == ""


def test_companion_sprite_interactions(qapp):
    sprite = CompanionSprite()
    sprite.set_state("listening")
    assert sprite.state == "listening"

    sprite.set_mouth_aperture(-15.0)
    assert sprite.mouth_aperture > 0.0

    # Geometry tracking
    geom = sprite.geometry()
    bubble = SpeechBubble()
    bubble.anchor_to(geom)
    assert bubble.x() > geom.x()


def test_settings_dialog_resizable(qapp):
    from PyQt6.QtCore import Qt

    from lucca.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    flags = dlg.windowFlags()
    assert bool(flags & Qt.WindowType.Window)
    assert bool(flags & Qt.WindowType.WindowMinMaxButtonsHint)
    assert bool(flags & Qt.WindowType.WindowCloseButtonHint)
    assert dlg.isSizeGripEnabled()
    assert dlg.minimumWidth() == 880
    assert dlg.minimumHeight() == 640


def test_telemetry_hud_lifecycle(qapp):
    from lucca.ui.telemetry_hud import TelemetryHUD

    hud = TelemetryHUD()
    # Timer should NOT be active while hidden
    assert not hud.poll_timer.isActive()
    assert not hud.isVisible()
    hud.close()


def test_codebase_claims_honest(qapp: QApplication) -> None:
    """F-UI-004: Ensure commorose and settings manual do not claim self-inspection."""
    from lucca.ui.app import get_commorose_actions
    from lucca.ui.settings_dialog import SettingsDialog

    # 1. Commorose actions check
    actions = get_commorose_actions()
    labels = [a.label for a in actions]
    assert "CODEBASE" not in labels
    assert "PROJECT" in labels
    project_action = next(a for a in actions if a.label == "PROJECT")
    assert "inspection" not in project_action.description.lower()
    assert "explorer" in project_action.description.lower()

    # 2. Settings dialog manual chapters
    dlg = SettingsDialog()
    for i in range(dlg.list_manual_chapters.count()):
        item = dlg.list_manual_chapters.item(i)
        assert item is not None
        assert "Codebase Self-Inspection" not in item.text()

    dlg._on_manual_chapter_selected(1)  # Avatar & Commorose chapter
    html_commorose = dlg.txt_manual_body.toHtml()
    assert "Safe read-only inspection of source repository" not in html_commorose
    assert "PROJECT" in html_commorose

    dlg._on_manual_chapter_selected(8)  # Chapter 9 (index 8)
    html_ch9 = dlg.txt_manual_body.toHtml()
    assert "Codebase Self-Inspection" not in html_ch9
    assert "Safe, read-only access to" not in html_ch9
