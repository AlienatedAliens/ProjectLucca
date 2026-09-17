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
