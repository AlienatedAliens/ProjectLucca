"""
Unit tests for PyQt6 desktop companion widgets (SpeechBubble, QuickChatBar, CompanionSprite).
Runs headlessly under offscreen QPA platform.
"""

import os

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton

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


@pytest.fixture(autouse=True)
def mock_server_health(monkeypatch):
    import lucca.ui.settings_dialog

    monkeypatch.setattr(
        lucca.ui.settings_dialog, "is_healthy", lambda host, port, timeout=1.0: False
    )


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


def test_speech_bubble_latency_badge(qapp):
    bubble = SpeechBubble()
    bubble.show()
    # Initially hidden and empty (no fabricated 382 ms)
    assert not bubble.latency_label.isVisible()
    assert bubble.latency_label.text() == ""

    # Setting a real latency displays it
    bubble.set_latency_ms(452.3)
    assert bubble.latency_label.isVisible()
    assert bubble.latency_label.text() == "452 ms"

    # Setting None or 0 hides it
    bubble.set_latency_ms(None)
    assert not bubble.latency_label.isVisible()
    assert bubble.latency_label.text() == ""


def test_speech_bubble_unbroken_string_geometry_clamp(qapp):
    bubble = SpeechBubble()
    bubble.show()

    # 500-char unbroken repetition token loop (e.g. ::*_*_*_*)
    degenerate_string = "::" + ("*_*" * 160)
    bubble.show_caption(degenerate_string, source="assistant", is_final=True)

    # Verify bubble remains clamped at 460px width
    assert bubble.width() == 460
    bubble.adjustSize()
    assert bubble.width() == 460

    # Verify no single unbroken token in the processed text exceeds 35 chars
    tokens = bubble.current_text.split(" ")
    assert all(len(t) <= 35 for t in tokens)


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
    assert dlg.minimumWidth() == 760
    assert dlg.minimumHeight() == 520


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


def test_sample_rule_validates(qapp: QApplication) -> None:
    """F-UI-005: Ensure shipped sample rule in SettingsDialog passes parse_rule and validate_rule_static."""
    from lucca.reasoning.scheme import parse_rule
    from lucca.reasoning.scheme.validator import validate_rule_static
    from lucca.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    assert "open-calculator-v1" in dlg.lisp_rules
    sample = dlg.lisp_rules["open-calculator-v1"]["code"]

    parsed = parse_rule(sample)
    assert parsed.rule_id == "open-calculator-v1"

    validated = validate_rule_static(sample)
    assert validated.rule_id == "open-calculator-v1"


def test_quit_publishes_offline(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """F-UI-002: Ensure UIApplication.quit() publishes ui.state=offline and sends ui.quit."""
    import time

    import zmq

    from lucca.core.config import get_config
    from lucca.core.ipc_schemas import decode_envelope
    from lucca.ui.app import UIApplication

    ctx = zmq.Context()
    ingest_pull = ctx.socket(zmq.PULL)
    ingest_port = ingest_pull.bind_to_random_port("tcp://127.0.0.1")

    cfg = get_config()
    monkeypatch.setattr(cfg.ipc, "ingest_port", ingest_port)

    app_instance = UIApplication()
    quit_called = []
    monkeypatch.setattr(app_instance.app, "quit", lambda: quit_called.append(True))
    time.sleep(0.05)
    try:
        app_instance.quit()
        assert quit_called == [True]

        received_types: list[str] = []
        received_payloads: list[dict[str, object]] = []
        for _ in range(5):
            if ingest_pull.poll(500) > 0:
                raw = ingest_pull.recv()
                env = decode_envelope(raw)
                if env.type in ("ui.state", "ui.quit"):
                    received_types.append(env.type)
                    received_payloads.append(dict(env.payload))
            if len(received_types) >= 2:
                break

        assert "ui.state" in received_types
        state_idx = received_types.index("ui.state")
        assert received_payloads[state_idx].get("state") == "offline"

        assert "ui.quit" in received_types
        quit_idx = received_types.index("ui.quit")
        assert received_payloads[quit_idx].get("reason") == "user"
    finally:
        ingest_pull.close(linger=0)
        ctx.destroy(linger=0)


def test_speech_bubble_pagination(qapp: QApplication) -> None:
    """Verifies that long speech text is cleanly split into discrete pages of at most 5 lines."""
    bubble = SpeechBubble()
    bubble.show()

    # Create text that easily exceeds 5 lines
    long_speech = (
        "In brief, I run locally on your PC with a 4-process topology. "
        "My model is a custom Mistral NeMo 12B Instruct Ablated served by llama-server.exe "
        "on the dGPU with flash attention. I also have Kokoro-82M TTS for speaking and "
        "Whisper for real-time speech transcription. My MicroScheme engine evaluates rules "
        "deterministically in sub-millisecond time. In addition, my memory system indexes "
        "both episodic and semantic embeddings locally via sqlite-vec."
    )
    bubble.show_caption(long_speech, source="assistant", is_final=True)

    assert len(bubble.pages) > 1
    # Verify each page has <= 5 lines
    for idx, page in enumerate(bubble.pages):
        lines = page.splitlines()
        assert len(lines) <= 5, f"Page {idx + 1} has {len(lines)} lines, expected <= 5"

    # Pager controls should be visible when len(pages) > 1
    assert bubble.btn_prev.isVisible()
    assert bubble.btn_next.isVisible()
    assert bubble.lbl_page.isVisible()


def test_speech_bubble_navigation(qapp: QApplication) -> None:
    """Verifies that prev/next page buttons update current page index and displayed text."""
    bubble = SpeechBubble()
    bubble.show()

    long_text = "Paragraph 1 sentence.\n\nParagraph 2 sentence.\n\nParagraph 3 sentence.\n\nParagraph 4 sentence.\n\nParagraph 5 sentence."
    bubble.show_caption(long_text, source="assistant", is_final=True)

    assert len(bubble.pages) >= 2
    total = len(bubble.pages)

    # By default on completion of stream, page is at the end or starts at 0
    # Let's test navigation explicitly
    bubble.current_page_idx = 0
    bubble._update_page_display()
    assert bubble.lbl_page.text() == f"[ 1 / {total} ]"
    assert bubble.btn_prev.isEnabled() is False
    assert bubble.btn_next.isEnabled() is True

    # Navigate to page 2
    bubble._next_page()
    assert bubble.current_page_idx == 1
    assert bubble.lbl_page.text() == f"[ 2 / {total} ]"
    assert bubble.btn_prev.isEnabled() is True

    # Navigate back to page 1
    bubble._prev_page()
    assert bubble.current_page_idx == 0
    assert bubble.lbl_page.text() == f"[ 1 / {total} ]"


def test_speech_bubble_persistence(qapp: QApplication) -> None:
    """Verifies that speech bubble remains persistent and does not auto-dismiss on timer."""
    bubble = SpeechBubble()
    bubble.show_caption("This is persistent dialogue.", source="assistant", is_final=True)

    assert bubble.isVisible() is True
    # Auto-dismiss timer must NOT be running for dialogue captions
    assert bubble.dismiss_timer.isActive() is False


def test_speech_bubble_close_button(qapp: QApplication) -> None:
    """Verifies that the header close button (✕) dismisses the persistent speech bubble."""
    bubble = SpeechBubble()
    bubble.show_caption("Close me please.", source="assistant", is_final=True)
    assert bubble.isVisible() is True

    bubble.btn_close.click()
    assert bubble.isVisible() is False


def test_speech_bubble_fixed_geometry(qapp: QApplication) -> None:
    """Verifies that bubble retains fixed 460x188 geometry preventing Win32 setGeometry fighting."""
    bubble = SpeechBubble()
    bubble.show()

    assert bubble.width() == 460
    assert bubble.height() == 188
    assert bubble.minimumSize() == bubble.maximumSize()

    # Even after displaying long text and calling adjustSize, geometry remains fixed
    bubble.show_caption("A" * 500, source="assistant", is_final=True)
    bubble.adjustSize()
    assert bubble.width() == 460
    assert bubble.height() == 188


def test_settings_dialog_scrollable_tabs(qapp: QApplication) -> None:
    """Verifies that all 11 tabs are wrapped in QScrollArea with widgetResizable enabled."""
    from PyQt6.QtWidgets import QScrollArea

    from lucca.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    assert dlg.tabs.count() == 11

    for i in range(dlg.tabs.count()):
        tab_widget = dlg.tabs.widget(i)
        assert isinstance(tab_widget, QScrollArea), f"Tab {i} is not a QScrollArea"
        assert tab_widget.widgetResizable() is True
        assert tab_widget.widget() is not None


def test_settings_dialog_center_containment(qapp: QApplication) -> None:
    """Verifies that center_on_screen positions dialog strictly within visible workarea."""
    from PyQt6.QtGui import QGuiApplication

    from lucca.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    dlg.center_on_screen()

    screen = QGuiApplication.primaryScreen()
    if screen:
        avail = screen.availableGeometry()
        assert dlg.x() >= avail.left()
        assert dlg.y() >= avail.top()
        assert dlg.x() + dlg.width() <= avail.right() + 20
        assert dlg.y() + dlg.height() <= avail.bottom() + 20


def test_settings_dialog_handle_save(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that _handle_save runs without AttributeError and passes user_archetypes."""
    import lucca.ui.settings_dialog as sd_module
    from lucca.ui.settings_dialog import SettingsDialog

    saved_kwargs: dict[str, object] = {}

    def mock_save(**kwargs: object) -> None:
        saved_kwargs.update(kwargs)

    monkeypatch.setattr(sd_module, "save_persona_to_config", mock_save)

    dlg = SettingsDialog()
    assert hasattr(dlg.tab_persona, "user_archetypes")
    assert dlg.tab_persona.user_archetypes == dlg.user_archetypes
    dlg._handle_save()
    assert "user_archetypes" in saved_kwargs


def test_settings_dialog_apply_vs_save_and_close(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies that Apply keeps the dialog open and Save & Close closes it."""
    import lucca.ui.settings_dialog as sd_module
    from lucca.ui.settings_dialog import SettingsDialog

    saved_calls: list[bool] = []

    def mock_save(**kwargs: object) -> None:
        saved_calls.append(True)

    monkeypatch.setattr(sd_module, "save_persona_to_config", mock_save)

    dlg = SettingsDialog()
    buttons = dlg.findChildren(QPushButton)
    btn_texts = [b.text() for b in buttons]
    assert "Apply" in btn_texts
    assert "✓ Save & Close" in btn_texts

    # Test Apply (does not accept/close dialog)
    dlg._handle_save(close_dialog=False)
    assert len(saved_calls) == 1
    assert "Configuration applied" in dlg.lbl_global_status.text()

    # Test Save & Close (accepts/closes dialog)
    dlg._handle_save(close_dialog=True)
    assert len(saved_calls) == 2


def test_settings_dialog_dsp_pitch_preservation(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies that DSPTab initializes with current persona pitch and saves it."""
    import lucca.ui.settings_dialog as sd_module
    from lucca.brain.prompt_builder import PersonaConfig
    from lucca.ui.settings_dialog import SettingsDialog

    mock_persona = PersonaConfig(
        dsp_pitch_semitones=3.0,
        dsp_enabled=True,
    )
    monkeypatch.setattr(sd_module, "get_persona_config", lambda: mock_persona)

    saved_kwargs: dict[str, object] = {}

    def mock_save(**kwargs: object) -> None:
        saved_kwargs.update(kwargs)

    monkeypatch.setattr(sd_module, "save_persona_to_config", mock_save)

    dlg = SettingsDialog()
    assert dlg.tab_dsp.slider_pitch.value() == 3
    assert "+3 semitones" in dlg.tab_dsp.lbl_pitch_val.text()

    dlg._handle_save(close_dialog=False)
    assert saved_kwargs.get("dsp_pitch_semitones") == 3.0
    assert saved_kwargs.get("dsp_enabled") is True


