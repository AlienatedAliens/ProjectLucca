"""
Project Lucca — Approved Application Whitelist Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

import json
import logging
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lucca.core.config import get_config

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade

_LOG = logging.getLogger(__name__)

FORBIDDEN_SHELLS = {"cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "wsl.exe"}


def _resolve_whitelist_path(config_path: Path | None) -> Path:
    if config_path is not None:
        return Path(config_path)
    cfg = get_config()
    cfg_file = cfg.resolve_path("config") / "tool_whitelist.toml"
    if not cfg_file.exists() and Path("config/tool_whitelist.toml").exists():
        cfg_file = Path("config/tool_whitelist.toml")
    return cfg_file


def load_whitelist_apps(config_path: Path | None = None) -> list[dict[str, str]]:
    """Loads approved application whitelist dynamically from tool_whitelist.toml (Spec 09 §6)."""
    cfg_file = _resolve_whitelist_path(config_path)

    apps: list[dict[str, str]] = []
    if cfg_file.exists():
        try:
            with open(cfg_file, "rb") as f:
                data = tomllib.load(f)
            apps_table = data.get("apps", {})
            for key, entry in apps_table.items():
                if isinstance(entry, dict):
                    name = str(
                        entry.get("aliases", [key])[0] if entry.get("aliases") else key
                    ).title()
                    path_str = str(entry.get("exe", ""))
                    tier = (
                        "Read-Only"
                        if "task" in key
                        else ("Network" if "browser" in key else "Trusted")
                    )
                    status = "Disabled" if entry.get("disabled", False) else "Active"
                    apps.append(
                        {
                            "key": key,
                            "name": name,
                            "path": path_str,
                            "tier": tier,
                            "status": status,
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("load_whitelist_apps_failed: %s", exc)

    if not apps:
        apps = [
            {
                "key": "calculator",
                "name": "Calculator",
                "path": "calc.exe",
                "tier": "Trusted",
                "status": "Active",
            },
            {
                "key": "notepad",
                "name": "Notepad",
                "path": "notepad.exe",
                "tier": "Trusted",
                "status": "Active",
            },
            {
                "key": "browser",
                "name": "Browser",
                "path": "msedge.exe",
                "tier": "Network",
                "status": "Active",
            },
            {
                "key": "terminal",
                "name": "Terminal",
                "path": "wt.exe",
                "tier": "Trusted",
                "status": "Active",
            },
            {
                "key": "task_manager",
                "name": "Task Manager",
                "path": "taskmgr.exe",
                "tier": "Read-Only",
                "status": "Active",
            },
        ]
    return apps


def save_whitelist_apps(apps: list[dict[str, str]], config_path: Path | None = None) -> None:
    """Saves approved application whitelist to tool_whitelist.toml, enforcing D-AUD-10."""
    cfg_file = _resolve_whitelist_path(config_path)

    lines = [
        "# Project Lucca — Approved Desktop Applications Whitelist",
        "# Spec 09 §6, D-AUD-10",
        "",
    ]
    for app in apps:
        key = app.get("key") or Path(app["path"]).stem.lower().replace(" ", "_")
        lines.append(f"[apps.{key}]")
        lines.append(f'exe = "{app["path"]}"')
        aliases = [app["name"].lower(), key]
        lines.append(f"aliases = {json.dumps(aliases)}")
        args = ["{file?}"] if "notepad" in key else (["{url?}"] if "browser" in key else [])
        lines.append(f"args = {json.dumps(args)}")
        single = "true" if ("calc" in key or "task" in key) else "false"
        lines.append(f"single_instance = {single}")
        if app.get("status") == "Disabled":
            lines.append("disabled = true")
        lines.append("")

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text("\n".join(lines), encoding="utf-8")


class ToolsTab(QWidget):
    """Tab 3: Approved Application Whitelist & Permissions (D-AUD-10)."""

    FORBIDDEN_SHELLS = FORBIDDEN_SHELLS

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self.whitelisted_apps: list[dict[str, str]] = load_whitelist_apps()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        grp_tools = QGroupBox("Approved Application Whitelist & Permissions", self)
        v_tools = QVBoxLayout(grp_tools)

        self.table_apps = QTableWidget(len(self.whitelisted_apps), 4, grp_tools)
        self.table_apps.setHorizontalHeaderLabels(
            ["App Name", "Executable Path", "Risk Tier", "Status"]
        )
        hdr_apps = self.table_apps.horizontalHeader()
        if hdr_apps is not None:
            hdr_apps.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for row, app in enumerate(self.whitelisted_apps):
            self.table_apps.setItem(row, 0, QTableWidgetItem(app["name"]))
            self.table_apps.setItem(row, 1, QTableWidgetItem(app["path"]))
            self.table_apps.setItem(row, 2, QTableWidgetItem(app["tier"]))
            self.table_apps.setItem(row, 3, QTableWidgetItem(app["status"]))

        v_tools.addWidget(self.table_apps)

        h_tools_act = QHBoxLayout()
        btn_add_app = QPushButton("➕ Add Application (.exe)", grp_tools)
        btn_add_app.clicked.connect(self._add_app_dialog)
        h_tools_act.addWidget(btn_add_app)

        btn_remove_app = QPushButton("🗑️ Remove Selected", grp_tools)
        btn_remove_app.clicked.connect(self._remove_app)
        h_tools_act.addWidget(btn_remove_app)

        btn_toggle_app = QPushButton("⚡ Toggle Active / Disabled", grp_tools)
        btn_toggle_app.clicked.connect(self._toggle_app_status)
        h_tools_act.addWidget(btn_toggle_app)

        h_tools_act.addStretch()
        v_tools.addLayout(h_tools_act)
        layout.addWidget(grp_tools)
        layout.addStretch()

    def _add_app_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Approved Executable", "C:\\\\", "Executables (*.exe);;All Files (*.*)"
        )
        if path:
            exe_name = Path(path).name.lower()
            if exe_name in self.FORBIDDEN_SHELLS:
                QMessageBox.warning(
                    self,
                    "Security Restriction (D-AUD-10)",
                    f"Shell execution via '{exe_name}' is strictly forbidden by Project Lucca security policy D-AUD-10.",
                )
                return

            name = Path(path).stem.replace("_", " ").title()
            key = Path(path).stem.lower().replace(" ", "_")
            new_entry = {
                "key": key,
                "name": name,
                "path": path,
                "tier": "User-Added",
                "status": "Active",
            }
            self.whitelisted_apps.append(new_entry)
            save_whitelist_apps(self.whitelisted_apps)

            row = self.table_apps.rowCount()
            self.table_apps.insertRow(row)
            self.table_apps.setItem(row, 0, QTableWidgetItem(name))
            self.table_apps.setItem(row, 1, QTableWidgetItem(path))
            self.table_apps.setItem(row, 2, QTableWidgetItem("User-Added"))
            self.table_apps.setItem(row, 3, QTableWidgetItem("Active"))

    def _remove_app(self) -> None:
        row = self.table_apps.currentRow()
        if row >= 0:
            if row < len(self.whitelisted_apps):
                self.whitelisted_apps.pop(row)
                save_whitelist_apps(self.whitelisted_apps)
            self.table_apps.removeRow(row)

    def _toggle_app_status(self) -> None:
        row = self.table_apps.currentRow()
        if row >= 0:
            item = self.table_apps.item(row, 3)
            if item:
                new_status = "Disabled" if item.text() == "Active" else "Active"
                item.setText(new_status)
                if row < len(self.whitelisted_apps):
                    self.whitelisted_apps[row]["status"] = new_status
                    save_whitelist_apps(self.whitelisted_apps)
