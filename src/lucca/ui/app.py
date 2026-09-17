"""
Project Lucca — UI Process (`lucca-ui`)
Spec 01 §1, ADR-005
"""

import sys
import threading
import time
from typing import Any

import zmq
from PyQt6.QtCore import QObject, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from lucca.core.config import get_config
from lucca.core.exceptions import IPCError
from lucca.core.ipc_schemas import (
    AudioRMSPayload,
    Envelope,
    PTTPressedPayload,
    PTTReleasedPayload,
    UICaptionPayload,
    UIConfigUpdatePayload,
    UIConfirmPayload,
    UIConfirmResultPayload,
    UIStatePayload,
    UIUserTextPayload,
    decode_envelope,
    encode_envelope,
)
from lucca.ui.input_bar import QuickChatBar
from lucca.ui.settings_dialog import SettingsDialog
from lucca.ui.speech_bubble import SpeechBubble
from lucca.ui.sprite import CompanionSprite


class UIBridge(QObject):
    state_changed = pyqtSignal(str)
    rms_received = pyqtSignal(float)
    caption_received = pyqtSignal(str, str, bool)  # text, source, is_final
    confirm_requested = pyqtSignal(str, str, float)  # prompt, summary, timeout_s


class UIApplication:
    def __init__(self) -> None:
        self.config = get_config()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # Active settings state
        self.active_voice = self.config.tts.voice
        self.active_speed = getattr(self.config.tts, "speed", 1.05)
        self.active_ptt_key = self.config.ptt.key
        self.is_always_on_top = True

        # IPC context & sockets
        self.ctx = zmq.Context()
        self.ingest_sock = self.ctx.socket(zmq.PUSH)
        self.ingest_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.ingest_port}")

        # Core widgets
        self.bridge = UIBridge()
        self.sprite = CompanionSprite()
        self.bubble = SpeechBubble(on_confirm=self._send_confirm_result)
        self.chat_bar = QuickChatBar(
            on_send_text=self._send_user_text,
            on_ptt_press=self._send_mouse_ptt_press,
            on_ptt_release=self._send_mouse_ptt_release,
        )
        self.settings_dialog: SettingsDialog | None = None

        # Wire bridge signals
        self.bridge.state_changed.connect(self.sprite.set_state)
        self.bridge.rms_received.connect(self.sprite.set_mouth_aperture)
        self.bridge.caption_received.connect(self._on_caption_received)
        self.bridge.confirm_requested.connect(self._on_confirm_requested)

        # Wire sprite interactions
        self.sprite.on_geometry_changed = self._on_sprite_moved
        self.sprite.on_toggle_chat = self._toggle_chat_bar
        self.sprite.on_context_menu = self._show_context_menu

        # Setup System Tray
        self._setup_tray()

        # ZeroMQ Bus Listener thread
        self.running = True
        self.zmq_thread = threading.Thread(target=self._bus_listener, name="ui-bus", daemon=True)
        self.zmq_thread.start()

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.app)
        menu = QMenu()

        chat_action = QAction("💬 Quick Chat Bar", menu)
        chat_action.triggered.connect(self._toggle_chat_bar)
        menu.addAction(chat_action)

        settings_action = QAction("⚙️ Settings & Diagnostics", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        toggle_action = QAction("Show / Hide Avatar", menu)
        toggle_action.triggered.connect(self._toggle_avatar)
        menu.addAction(toggle_action)

        reset_action = QAction("🔁 Reset Avatar Position", menu)
        reset_action.triggered.connect(self.sprite.reset_position)
        menu.addAction(reset_action)

        menu.addSeparator()

        quit_action = QAction("Quit Lucca", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Project Lucca — Desktop Companion")
        self.tray.show()

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #313244;
                color: #89b4fa;
            }
            QMenu::separator {
                height: 1px;
                background: #313244;
                margin: 4px 6px;
            }
        """)

        chat_action = QAction("💬 Quick Chat Bar (Double-Click)", menu)
        chat_action.triggered.connect(self._toggle_chat_bar)
        menu.addAction(chat_action)

        settings_action = QAction("⚙️ Settings & Diagnostics...", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        top_action = QAction("📌 Always on Top", menu)
        top_action.setCheckable(True)
        top_action.setChecked(self.is_always_on_top)
        top_action.triggered.connect(self._toggle_always_on_top)
        menu.addAction(top_action)

        reset_action = QAction("🔁 Reset Position", menu)
        reset_action.triggered.connect(self.sprite.reset_position)
        menu.addAction(reset_action)

        menu.addSeparator()

        quit_action = QAction("✕ Quit Lucca", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        menu.exec(pos)

    def _open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(
                current_voice=self.active_voice,
                current_speed=self.active_speed,
                current_ptt_key=self.active_ptt_key,
                on_save_config=self._send_config_update,
            )
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _toggle_always_on_top(self) -> None:
        self.is_always_on_top = self.sprite.toggle_always_on_top()

    def _toggle_avatar(self) -> None:
        if self.sprite.isVisible():
            self.sprite.hide()
            self.bubble.hide()
            self.chat_bar.hide()
        else:
            self.sprite.show()

    def _get_screen_geometry(self) -> QRect | None:
        screen = self.sprite.screen()
        return screen.geometry() if screen is not None else None

    def _toggle_chat_bar(self) -> None:
        self.chat_bar.toggle()
        self.chat_bar.anchor_to(self.sprite.geometry())

    def _on_sprite_moved(self) -> None:
        geom = self.sprite.geometry()
        screen_geom = self._get_screen_geometry()
        self.bubble.anchor_to(geom, screen_geom)
        self.chat_bar.anchor_to(geom)

    def _on_caption_received(self, text: str, source: str, is_final: bool) -> None:
        geom = self.sprite.geometry()
        screen_geom = self._get_screen_geometry()
        self.bubble.show_caption(text, source=source, is_final=is_final)
        self.bubble.anchor_to(geom, screen_geom)

    def _on_confirm_requested(self, prompt: str, summary: str, timeout_s: float) -> None:
        geom = self.sprite.geometry()
        screen_geom = self._get_screen_geometry()
        self.bubble.show_confirmation(prompt, summary)
        self.bubble.anchor_to(geom, screen_geom)

    def _send_user_text(self, text: str) -> None:
        geom = self.sprite.geometry()
        screen_geom = self._get_screen_geometry()
        self.bubble.show_caption(text, source="user", is_final=True)
        self.bubble.anchor_to(geom, screen_geom)

        env = Envelope(
            type="ui.user_text",
            trace_id="",
            ts_ns=time.monotonic_ns(),
            src="ui",
            payload=UIUserTextPayload(text=text).model_dump(),
        )
        self._send_ingest(env)

    def _send_confirm_result(self, accepted: bool) -> None:
        env = Envelope(
            type="ui.confirm_result",
            trace_id="",
            ts_ns=time.monotonic_ns(),
            src="ui",
            payload=UIConfirmResultPayload(accepted=accepted, via="click").model_dump(),
        )
        self._send_ingest(env)

    def _send_config_update(self, new_config: dict[str, Any]) -> None:
        self.active_voice = str(new_config.get("voice", self.active_voice))
        self.active_speed = float(new_config.get("speed", self.active_speed))
        self.active_ptt_key = str(new_config.get("ptt_key", self.active_ptt_key))

        env = Envelope(
            type="ui.config_update",
            trace_id="",
            ts_ns=time.monotonic_ns(),
            src="ui",
            payload=UIConfigUpdatePayload(
                voice=self.active_voice,
                speed=self.active_speed,
                ptt_key=self.active_ptt_key,
            ).model_dump(),
        )
        self._send_ingest(env)

    def _send_mouse_ptt_press(self) -> None:
        env = Envelope(
            type="ptt.pressed",
            trace_id="",
            ts_ns=time.monotonic_ns(),
            src="ui",
            payload=PTTPressedPayload(t_ns=time.monotonic_ns()).model_dump(),
        )
        self._send_ingest(env)

    def _send_mouse_ptt_release(self) -> None:
        env = Envelope(
            type="ptt.released",
            trace_id="",
            ts_ns=time.monotonic_ns(),
            src="ui",
            payload=PTTReleasedPayload(
                t_ns=time.monotonic_ns(),
                capture_seq_start=0,
                capture_seq_end=0,
                duration_ms=500.0,
                vad_speech_ms=500.0,
            ).model_dump(),
        )
        self._send_ingest(env)

    def _send_ingest(self, env: Envelope) -> None:
        try:
            self.ingest_sock.send(encode_envelope(env), zmq.NOBLOCK)
        except zmq.ZMQError as exc:
            print(f"[UI] Ingest socket send error: {exc}", flush=True)

    def _bus_listener(self) -> None:
        ctx = zmq.Context()
        bus_sock = ctx.socket(zmq.SUB)
        bus_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.bus_port}")
        bus_sock.setsockopt_string(zmq.SUBSCRIBE, "")

        poller = zmq.Poller()
        poller.register(bus_sock, zmq.POLLIN)

        while self.running:
            try:
                socks = dict(poller.poll(timeout=100))
            except zmq.ZMQError:
                if not self.running:
                    break
                continue

            if bus_sock in socks:
                try:
                    raw = bus_sock.recv()
                    env = decode_envelope(raw)
                    if env.type == "ui.state":
                        p_ui = UIStatePayload.model_validate(env.payload)
                        self.bridge.state_changed.emit(p_ui.state)
                    elif env.type == "ui.caption":
                        p_cap = UICaptionPayload.model_validate(env.payload)
                        self.bridge.caption_received.emit(p_cap.text, p_cap.source, p_cap.is_final)
                    elif env.type == "ui.confirm":
                        p_conf = UIConfirmPayload.model_validate(env.payload)
                        self.bridge.confirm_requested.emit(
                            p_conf.prompt_text, p_conf.action_summary, p_conf.timeout_s
                        )
                    elif env.type == "audio.rms":
                        p_rms = AudioRMSPayload.model_validate(env.payload)
                        self.bridge.rms_received.emit(p_rms.dbfs)
                except (IPCError, zmq.ZMQError, ValueError):
                    pass

        bus_sock.close(linger=0)
        ctx.destroy(linger=0)

    def run(self) -> int:
        self.sprite.reset_position()
        self.sprite.show()
        geom = self.sprite.geometry()
        screen_geom = self._get_screen_geometry()
        self.bubble.anchor_to(geom, screen_geom)
        self.chat_bar.anchor_to(geom)
        return self.app.exec()

    def quit(self) -> None:
        self.running = False
        try:
            self.ingest_sock.close(linger=0)
            self.ctx.destroy(linger=0)
        except Exception:  # noqa: BLE001, S110
            pass
        self.app.quit()


def main() -> None:
    ui_app = UIApplication()
    sys.exit(ui_app.run())


if __name__ == "__main__":
    main()
