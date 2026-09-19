"""
Project Lucca — UI Process (`lucca-ui`)
Spec 01 §1, ADR-005
"""

import ctypes
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import zmq
from PyQt6.QtCore import QMetaObject, QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from lucca.brain.prompt_builder import get_persona
from lucca.core.config import get_config
from lucca.core.exceptions import IPCError
from lucca.core.ipc_schemas import (
    AudioRMSPayload,
    Envelope,
    UICaptionPayload,
    UIConfigUpdatePayload,
    UIConfirmPayload,
    UIConfirmResultPayload,
    UIQuitPayload,
    UIStatePayload,
    UIUserTextPayload,
    decode_envelope,
    encode_envelope,
)
from lucca.core.trace import now_ns
from lucca.ui.commorose import CommoroseAction, CommoroseRadialMenu
from lucca.ui.input_bar import QuickChatBar
from lucca.ui.settings_dialog import SettingsDialog
from lucca.ui.speech_bubble import SpeechBubble
from lucca.ui.sprite import CompanionSprite
from lucca.ui.telemetry_hud import TelemetryHUD
from lucca.ui.theme import CHRONO_TRIGGER_STYLE_SHEET


class UIBridge(QObject):
    state_changed = pyqtSignal(str)
    rms_received = pyqtSignal(float)
    caption_received = pyqtSignal(str, str, bool)  # text, source, is_final
    confirm_requested = pyqtSignal(str, str, float)  # prompt, summary, timeout_s


def get_commorose_actions(
    open_dir_fn: Callable[[str], None] | None = None,
    toggle_hud_fn: Callable[[], None] | None = None,
    open_settings_fn: Callable[[], None] | None = None,
    toggle_chat_fn: Callable[[], None] | None = None,
    open_tab_fn: Callable[[int], None] | None = None,
) -> list[CommoroseAction]:
    def _default_open_dir(path: str) -> None:
        subprocess.Popen(["explorer.exe", path])  # noqa: S603, S607

    _open_dir: Callable[[str], None] = open_dir_fn or _default_open_dir
    _toggle_hud: Callable[[], None] = toggle_hud_fn or (lambda: None)
    _open_settings: Callable[[], None] = open_settings_fn or (lambda: None)
    _toggle_chat: Callable[[], None] = toggle_chat_fn or (lambda: None)
    _open_tab: Callable[[int], None] = open_tab_fn or (lambda _idx: None)

    project_root = str(Path(__file__).resolve().parents[3])
    home_dir = str(get_config().home_dir)

    def _open_home() -> None:
        _open_dir(home_dir)

    def _open_project() -> None:
        _open_dir(project_root)

    def _tab_0() -> None:
        _open_tab(0)

    def _tab_1() -> None:
        _open_tab(1)

    def _tab_3() -> None:
        _open_tab(3)

    return [
        CommoroseAction("TELEMETRY", "📊", _toggle_hud, "Toggle live hardware telemetry HUD"),
        CommoroseAction("SETTINGS", "⚙️", _open_settings, "Open 10-tab configuration suite"),
        CommoroseAction("CHAT BAR", "💬", _toggle_chat, "Toggle dialogue and chat input"),
        CommoroseAction(
            "FOLDERS",
            "📁",
            _open_home,
            "Open Project Lucca home directory",
        ),
        CommoroseAction("PERSONA", "🧠", _tab_0, "Switch persona profile"),
        CommoroseAction("VOICE", "🎙️", _tab_1, "Voice synthesis blender"),
        CommoroseAction("TOOLS", "🛠️", _tab_3, "Application whitelist studio"),
        CommoroseAction(
            "PROJECT",
            "💻",
            _open_project,
            "Open project directory in Explorer",
        ),
    ]


class UIApplication:
    def __init__(self) -> None:
        # Set Windows AppUserModelID so taskbar and antivirus see distinct application
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ProjectLucca.DesktopCompanion.0.2"
            )
        except Exception:  # noqa: BLE001, S110
            pass

        self.config = get_config()
        existing_app = QApplication.instance()
        if isinstance(existing_app, QApplication):
            self.app = existing_app
        else:
            self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setStyleSheet(CHRONO_TRIGGER_STYLE_SHEET)

        # Set application icon
        self.app_icon: QIcon | None = None
        icon_p = Path("assets/icon.png")
        if not icon_p.exists():
            icon_p = self.config.home_dir / "assets" / "icon.png"
        if icon_p.exists():
            self.app_icon = QIcon(str(icon_p))
            self.app.setWindowIcon(self.app_icon)

        # Active settings state
        self.active_voice = self.config.tts.voice
        self.active_speed = getattr(self.config.tts, "speed", 1.05)
        self.active_ptt_key = self.config.ptt.key
        self.is_always_on_top = True

        # IPC context & sockets
        self.ctx = zmq.Context()
        self.ingest_sock = self.ctx.socket(zmq.PUSH)
        self.ingest_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.ingest_port}")
        self.bus_pub_sock = self.ctx.socket(zmq.PUB)
        self.bus_pub_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.bus_port}")

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
        self.telemetry_hud = TelemetryHUD()

        def _open_dir_cmd(path: str) -> None:
            subprocess.Popen(["explorer.exe", path])  # noqa: S603, S607

        commorose_actions = get_commorose_actions(
            open_dir_fn=_open_dir_cmd,
            toggle_hud_fn=self._toggle_telemetry_hud,
            open_settings_fn=self._open_settings,
            toggle_chat_fn=self._toggle_dialogue_and_chat,
            open_tab_fn=self._open_settings_tab,
        )
        self.commorose = CommoroseRadialMenu(commorose_actions)

        # Wire bridge signals
        self.bridge.state_changed.connect(self.sprite.set_state)
        self.bridge.rms_received.connect(self.sprite.set_mouth_aperture)
        self.bridge.caption_received.connect(self._on_caption_received)
        self.bridge.confirm_requested.connect(self._on_confirm_requested)

        # Wire sprite interactions: Single click -> chat/subtitles, Double click -> Commorose
        self.sprite.on_geometry_changed = self._on_sprite_moved
        self.sprite.on_toggle_chat = self._toggle_dialogue_and_chat
        self.sprite.on_toggle_commorose = self._toggle_commorose
        self.sprite.on_context_menu = self._show_context_menu

        # Setup System Tray
        self.tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
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
        if self.app_icon is not None:
            self.tray.setIcon(self.app_icon)
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
            persona = get_persona()
            self.settings_dialog = SettingsDialog(
                current_voice=self.active_voice,
                current_speed=self.active_speed,
                current_ptt_key=self.active_ptt_key,
                current_archetype=persona.archetype,
                current_formality=persona.formality,
                current_custom_prompt=persona.custom_prompt,
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

    def _toggle_commorose(self, center: QPoint | None = None) -> None:
        """Toggles the battlefield-style concentric Commorose radial menu."""
        if center is None:
            center = self.sprite.geometry().center()
        self.commorose.toggle(center)

    def _toggle_telemetry_hud(self) -> None:
        """Toggles the Chrono Trigger live hardware telemetry HUD."""
        self.telemetry_hud.toggle()
        if self.telemetry_hud.isVisible():
            sprite_geom = self.sprite.geometry()
            screen = self.sprite.screen()
            screen_geom = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
            target_x = max(
                20,
                min(sprite_geom.x() - 150, screen_geom.width() - self.telemetry_hud.width() - 20),
            )
            target_y = max(40, sprite_geom.y() - self.telemetry_hud.height() - 30)
            self.telemetry_hud.move(target_x, target_y)
            self.telemetry_hud.raise_()
            self.telemetry_hud.activateWindow()

    def _toggle_dialogue_and_chat(self) -> None:
        """Single-click toggle: brings up subtitle dialogue box and quick chat input bar."""
        geom = self.sprite.geometry()
        screen_geom = self._get_screen_geometry()
        if self.chat_bar.isVisible():
            self.chat_bar.hide()
            self.bubble.hide()
        else:
            if not self.bubble.current_text:
                self.bubble.show_caption(
                    "I'm listening! You can type here or hold 🎙️ to speak.",
                    source="assistant",
                    is_final=True,
                )
            else:
                self.bubble.show()
            self.bubble.anchor_to(geom, screen_geom)
            self.chat_bar.show()
            self.chat_bar.anchor_to(geom)
            self.chat_bar.input_field.setFocus()
            self.chat_bar.raise_()
            self.chat_bar.activateWindow()

    def _open_settings_tab(self, index: int) -> None:
        """Opens settings dialog directly to a specific tab index."""
        self._open_settings()
        if self.settings_dialog is not None and hasattr(self.settings_dialog, "tabs"):
            self.settings_dialog.tabs.setCurrentIndex(index)

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
            ts_ns=now_ns(),
            src="ui",
            payload=UIUserTextPayload(text=text).model_dump(),
        )
        self._send_ingest(env)

    def _send_confirm_result(self, accepted: bool) -> None:
        env = Envelope(
            type="ui.confirm_result",
            trace_id="",
            ts_ns=now_ns(),
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
            ts_ns=now_ns(),
            src="ui",
            payload=UIConfigUpdatePayload(
                voice=self.active_voice,
                speed=self.active_speed,
                ptt_key=self.active_ptt_key,
                persona_archetype=new_config.get("persona_archetype"),
                formality=new_config.get("formality"),
                custom_system_prompt=new_config.get("custom_system_prompt"),
                llm_model=new_config.get("llm_model"),
            ).model_dump(),
        )
        self._send_ingest(env)

    def _send_mouse_ptt_press(self) -> None:
        self._talk_press_time = time.monotonic()
        env = Envelope(
            type="ui.talk_press",
            trace_id="",
            ts_ns=now_ns(),
            src="ui",
            payload={},
        )
        self._send_ingest(env)

    def _send_mouse_ptt_release(self) -> None:
        t0 = getattr(self, "_talk_press_time", time.monotonic() - 1.0)
        dur_ms = max(100.0, (time.monotonic() - t0) * 1000.0)
        env = Envelope(
            type="ui.talk_release",
            trace_id="",
            ts_ns=now_ns(),
            src="ui",
            payload={"duration_ms": dur_ms},
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
                    elif env.type == "sys.shutdown":
                        self.running = False
                        self.bridge.state_changed.emit("offline")
                        QMetaObject.invokeMethod(
                            self.app, "quit", Qt.ConnectionType.QueuedConnection
                        )
                        break
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
        if hasattr(self, "zmq_thread") and self.zmq_thread.is_alive():
            self.zmq_thread.join(timeout=1.0)

        try:
            if hasattr(self, "tray") and self.tray is not None:
                self.tray.hide()
            if hasattr(self, "telemetry_hud"):
                self.telemetry_hud.close()
            if hasattr(self, "commorose"):
                self.commorose.close()
            if hasattr(self, "settings_dialog") and self.settings_dialog is not None:
                self.settings_dialog.close()
            if hasattr(self, "chat_bar"):
                self.chat_bar.close()
            if hasattr(self, "bubble"):
                self.bubble.close()
            if hasattr(self, "sprite"):
                self.sprite.close()
        except Exception:  # noqa: BLE001, S110
            pass

        try:
            env_offline = Envelope(
                type="ui.state",
                trace_id="",
                ts_ns=now_ns(),
                src="ui",
                payload=UIStatePayload(state="offline", detail="user_quit").model_dump(),
            )
            self._send_ingest(env_offline)
            self.bus_pub_sock.send(encode_envelope(env_offline), zmq.NOBLOCK)
        except Exception:  # noqa: BLE001, S110
            pass

        try:
            env_quit = Envelope(
                type="ui.quit",
                trace_id="",
                ts_ns=now_ns(),
                src="ui",
                payload=UIQuitPayload(reason="user").model_dump(),
            )
            self._send_ingest(env_quit)
        except Exception:  # noqa: BLE001, S110
            pass

        time.sleep(0.05)
        try:
            self.ingest_sock.close(linger=100)
            self.bus_pub_sock.close(linger=100)
            self.ctx.destroy(linger=100)
        except Exception:  # noqa: BLE001, S110
            pass

        self.app.quit()


def main() -> None:
    ui_app = UIApplication()
    sys.exit(ui_app.run())


if __name__ == "__main__":
    main()
