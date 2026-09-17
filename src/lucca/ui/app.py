"""
Project Lucca — UI Process (`lucca-ui`)
Spec 01 §1, ADR-005
"""

import sys
import threading

import zmq
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from lucca.core.config import get_config
from lucca.core.exceptions import IPCError
from lucca.core.ipc_schemas import (
    AudioRMSPayload,
    UIStatePayload,
    decode_envelope,
)
from lucca.ui.sprite import CompanionSprite


class UIBridge(QObject):
    state_changed = pyqtSignal(str)
    rms_received = pyqtSignal(float)


class UIApplication:
    def __init__(self) -> None:
        self.config = get_config()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.bridge = UIBridge()
        self.sprite = CompanionSprite()

        self.bridge.state_changed.connect(self.sprite.set_state)
        self.bridge.rms_received.connect(self.sprite.set_mouth_aperture)

        # Setup System Tray
        self._setup_tray()

        # ZeroMQ thread
        self.running = True
        self.zmq_thread = threading.Thread(target=self._bus_listener, name="ui-bus", daemon=True)
        self.zmq_thread.start()

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.app)
        menu = QMenu()

        toggle_action = QAction("Show / Hide Avatar", menu)
        toggle_action.triggered.connect(self._toggle_avatar)
        menu.addAction(toggle_action)

        menu.addSeparator()
        quit_action = QAction("Quit Lucca", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Project Lucca — Desktop Companion")
        self.tray.show()

    def _toggle_avatar(self) -> None:
        if self.sprite.isVisible():
            self.sprite.hide()
        else:
            self.sprite.show()

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
                    elif env.type == "audio.rms":
                        p_rms = AudioRMSPayload.model_validate(env.payload)
                        self.bridge.rms_received.emit(p_rms.dbfs)
                except (IPCError, zmq.ZMQError, ValueError):
                    pass

        bus_sock.close(linger=0)
        ctx.destroy(linger=0)

    def run(self) -> int:
        self.sprite.show()
        return self.app.exec()

    def quit(self) -> None:
        self.running = False
        self.app.quit()


def main() -> None:
    ui_app = UIApplication()
    sys.exit(ui_app.run())


if __name__ == "__main__":
    main()
