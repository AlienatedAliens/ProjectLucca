"""
Project Lucca — MicroScheme LISP Reasoning Studio Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import JsonValue
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lucca.core.schemas import RuleState, SkillMeta
from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade

_LOG = logging.getLogger(__name__)


class LispTab(QWidget):
    """Tab 4: MicroScheme LISP Reasoning Studio."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade

        # Canonical MicroScheme rules (seed demo) + live skill registry
        self.lisp_rules: dict[str, dict[str, JsonValue]] = {
            "open-calculator-v1": {
                "category": "Tools & Execution",
                "purpose": "Deterministic rule to launch calculator when requested and not already running.",
                "priority": 10,
                "state": "ACTIVE",
                "code": (
                    '(rule "open-calculator-v1"\n'
                    '  :when (and (intent= "launch_app")\n'
                    '             (entity-has? "app" "calculator")\n'
                    '             (not (app-running? "calculator")))\n'
                    '  :plan (list (tool "launch_app" :app "calculator")\n'
                    '              (say "Opening the calculator."))\n'
                    "  :priority 10)"
                ),
            },
        }
        self._load_lisp_registry()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        grp_lisp = QGroupBox("MicroScheme Domain-Specific Reasoning Pathways", self)
        v_lisp = QVBoxLayout(grp_lisp)

        # Category Filter
        h_filter = QHBoxLayout()
        h_filter.addWidget(QLabel("Category Filter:", grp_lisp))
        self.combo_lisp_cat = QComboBox(grp_lisp)
        self.combo_lisp_cat.addItem("All Categories")
        self._refresh_lisp_categories()
        self.combo_lisp_cat.currentTextChanged.connect(self._populate_lisp_table)
        h_filter.addWidget(self.combo_lisp_cat)
        h_filter.addStretch()

        btn_add_rule = QPushButton("➕ Add Reasoning Pathway", grp_lisp)
        btn_add_rule.clicked.connect(self._add_new_rule_dialog)
        h_filter.addWidget(btn_add_rule)
        v_lisp.addLayout(h_filter)

        # Rules Table
        self.table_lisp = QTableWidget(len(self.lisp_rules), 5, grp_lisp)
        self.table_lisp.setHorizontalHeaderLabels(
            ["Category", "Pathway ID", "Purpose", "Priority", "Status"]
        )
        hdr_lisp = self.table_lisp.horizontalHeader()
        if hdr_lisp is not None:
            hdr_lisp.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_lisp.cellClicked.connect(self._on_rule_selected)
        v_lisp.addWidget(self.table_lisp)

        self._populate_lisp_table()

        # In-Place S-Expression Code Editor
        v_lisp.addWidget(QLabel("Canonical MicroScheme S-Expression Definition:", grp_lisp))
        self.txt_rule_code = QPlainTextEdit(grp_lisp)
        self.txt_rule_code.setFont(QFont("Consolas", 10))
        self.txt_rule_code.setMaximumHeight(130)
        v_lisp.addWidget(self.txt_rule_code)

        # Validation and Action Controls
        h_lisp_acts = QHBoxLayout()
        btn_validate_rule = QPushButton("✓ Validate AST Syntax", grp_lisp)
        btn_validate_rule.clicked.connect(self._validate_current_rule)
        h_lisp_acts.addWidget(btn_validate_rule)

        btn_test_eval = QPushButton("▶ Test Evaluation", grp_lisp)
        btn_test_eval.clicked.connect(self._test_eval_rule)
        h_lisp_acts.addWidget(btn_test_eval)

        btn_save_rule = QPushButton("💾 Save Pathway Definition", grp_lisp)
        btn_save_rule.clicked.connect(self._save_selected_rule)
        h_lisp_acts.addWidget(btn_save_rule)

        btn_retire_rule = QPushButton("🗑️ Retire / Remove", grp_lisp)
        btn_retire_rule.clicked.connect(self._retire_selected_rule)
        h_lisp_acts.addWidget(btn_retire_rule)

        h_lisp_acts.addStretch()
        v_lisp.addLayout(h_lisp_acts)

        self.lbl_rule_status = QLabel("Select a pathway to inspect or edit definition.", grp_lisp)
        self.lbl_rule_status.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-style: italic;")
        v_lisp.addWidget(self.lbl_rule_status)

        layout.addWidget(grp_lisp)

        # Shadow Telemetry & Contrastive Evaluation Group (Rung L2)
        grp_shadow = QGroupBox("Shadow Telemetry & Contrastive Evaluation (Rung L2)", self)
        v_shadow = QVBoxLayout(grp_shadow)

        h_replay = QHBoxLayout()
        self.btn_lisp_replay = QPushButton("▶ Run Offline Replay (50 Episodes)", grp_shadow)
        self.btn_lisp_replay.clicked.connect(self._run_lisp_replay)
        h_replay.addWidget(self.btn_lisp_replay)

        self.lbl_replay_status = QLabel(
            "Select a pathway to run Dream-RSI offline replay.", grp_shadow
        )
        self.lbl_replay_status.setStyleSheet(f"color: {CT_GOLD_TEXT};")
        h_replay.addWidget(self.lbl_replay_status)
        h_replay.addStretch()
        v_shadow.addLayout(h_replay)

        h_metrics = QHBoxLayout()
        self.lbl_lisp_clusters = QLabel("Quarantine Clusters: N/A", grp_shadow)
        self.lbl_lisp_agreement = QLabel("Agreed Rate (95% CI): N/A", grp_shadow)
        self.lbl_lisp_mcnemar = QLabel("Paired McNemar (b/c): N/A", grp_shadow)
        self.lbl_lisp_reliability = QLabel("Execution-Reliability (S1): N/A", grp_shadow)

        h_metrics.addWidget(self.lbl_lisp_clusters)
        h_metrics.addWidget(self.lbl_lisp_agreement)
        h_metrics.addWidget(self.lbl_lisp_mcnemar)
        h_metrics.addWidget(self.lbl_lisp_reliability)
        h_metrics.addStretch()
        v_shadow.addLayout(h_metrics)

        lbl_disclaimer = QLabel(
            "Note: All reliability rates represent Execution-Reliability Rate (S1) "
            "(process non-crash / schema compliance), never conflated with task success.",
            grp_shadow,
        )
        lbl_disclaimer.setStyleSheet("color: #888888; font-size: 10px; font-style: italic;")
        v_shadow.addWidget(lbl_disclaimer)

        layout.addWidget(grp_shadow)

    def _load_lisp_registry(self) -> None:
        skills_root = self.facade.get_skills_dir()
        retired_root = self.facade.get_retired_dir()
        live_rules = self.facade.get_rules()

        for root, default_status in ((skills_root, None), (retired_root, "RETIRED")):
            if not root or not root.exists() or not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if not child.is_dir() or child.name.startswith("_") or child.name.startswith("."):
                    continue
                meta_file = child / "meta_info.json"
                plan_file = child / "plan.scm"
                if not meta_file.exists():
                    continue
                try:
                    meta = SkillMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    _LOG.debug("lisp_studio_meta_parse_failed: %s", exc)
                    continue
                code = plan_file.read_text(encoding="utf-8") if plan_file.exists() else ""
                status = default_status or meta.status
                if meta.id in live_rules:
                    status = live_rules[meta.id].status
                cats = ", ".join(meta.categories) if meta.categories else "-"
                self.lisp_rules[meta.id] = {
                    "category": cats,
                    "purpose": meta.description or meta.intent,
                    "priority": 10,
                    "state": status,
                    "code": code,
                    "on_disk": True,
                }

    def _refresh_lisp_categories(self) -> None:
        cats: set[str] = set()
        for data in self.lisp_rules.values():
            for raw_part in str(data["category"]).split(","):
                part = raw_part.strip()
                if part and part != "-":
                    cats.add(part)
        current = self.combo_lisp_cat.currentText()
        self.combo_lisp_cat.blockSignals(True)
        self.combo_lisp_cat.clear()
        self.combo_lisp_cat.addItem("All Categories")
        for c in sorted(cats):
            self.combo_lisp_cat.addItem(c)
        idx = self.combo_lisp_cat.findText(current)
        self.combo_lisp_cat.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_lisp_cat.blockSignals(False)

    def _populate_lisp_table(self, filter_cat: str = "All Categories") -> None:
        self.table_lisp.setRowCount(0)
        for rule_id, data in self.lisp_rules.items():
            cat = str(data["category"])
            if filter_cat != "All Categories" and filter_cat not in cat:
                continue

            row = self.table_lisp.rowCount()
            self.table_lisp.insertRow(row)
            self.table_lisp.setItem(row, 0, QTableWidgetItem(cat))
            self.table_lisp.setItem(row, 1, QTableWidgetItem(rule_id))
            self.table_lisp.setItem(row, 2, QTableWidgetItem(str(data["purpose"])))
            self.table_lisp.setItem(row, 3, QTableWidgetItem(str(data["priority"])))
            self.table_lisp.setItem(row, 4, QTableWidgetItem(str(data["state"])))

    def _on_rule_selected(self, row: int, col: int) -> None:
        item = self.table_lisp.item(row, 1)
        if not item:
            return
        rule_id = item.text()
        if rule_id in self.lisp_rules:
            data = self.lisp_rules[rule_id]
            self.txt_rule_code.setPlainText(str(data["code"]))
            self.lbl_rule_status.setText(f"Loaded definition for [{rule_id}] ({data['category']}).")
        self._update_shadow_telemetry(rule_id)

    def _run_lisp_replay(self) -> None:
        row = self.table_lisp.currentRow()
        if row < 0:
            self.lbl_replay_status.setText("Select a rule in the table first.")
            return
        item = self.table_lisp.item(row, 1)
        if not item:
            return
        rule_id = item.text()
        try:
            report = self.facade.replay_rule_candidate(rule_id)
            if report.passed:
                self.lbl_replay_status.setText(
                    f"✓ Replay PASSED: {report.n_real} episodes, 0 errors, {report.fires} fires."
                )
                self.lbl_replay_status.setStyleSheet("color: #44dd44;")
            else:
                reason = report.reasons[0] if report.reasons else "Replay failed."
                self.lbl_replay_status.setText(f"✗ Replay REFUSED: {reason}")
                self.lbl_replay_status.setStyleSheet("color: #ff5555;")
        except Exception as exc:
            _LOG.debug("run_lisp_replay_failed: %s", exc)
            self.lbl_replay_status.setText("Database / Lifecycle manager not initialized.")

    def _update_shadow_telemetry(self, rule_id: str) -> None:
        try:
            summary = self.facade.get_rule_contrastive_summary(rule_id)
        except Exception as exc:
            _LOG.debug("get_rule_contrastive_summary_failed: %s", exc)
            return

        total_turns = int(summary.get("total_turns", 0))
        agreed_rate = float(summary.get("agreed_rate", 0.0))
        ag_interval = summary.get("agreed_interval", [0.0, 1.0])
        b = int(summary.get("b_rule_better", 0))
        c = int(summary.get("c_core_better", 0))
        p_val = float(summary.get("mcnemar_p_value", 1.0))
        rel_rate = float(summary.get("rule_reliability_rate", 0.0))
        rel_interval = summary.get("rule_reliability_interval", [0.0, 1.0])

        live_rules = self.facade.get_rules()
        rule = live_rules.get(rule_id)
        n_clusters = len(rule.success_clusters) if rule else 0
        fail_ucl = self.facade.rule_of_three_ucl(n_clusters)
        self.lbl_lisp_clusters.setText(
            f"Quarantine Clusters: {n_clusters}/5 (0 err -> fail <= {fail_ucl:.0%})"
        )

        if total_turns > 0 and isinstance(ag_interval, list) and len(ag_interval) == 2:
            ag_lb_str = f"{float(ag_interval[0]):.1%}"
            ag_ub_str = f"{float(ag_interval[1]):.1%}"
            self.lbl_lisp_agreement.setText(
                f"Agreed Rate (95% CI): {agreed_rate:.1%} [{ag_lb_str}, {ag_ub_str}]"
            )
            self.lbl_lisp_mcnemar.setText(f"Paired McNemar (b={b}, c={c}): p={p_val:.3f}")
            if isinstance(rel_interval, list) and len(rel_interval) == 2:
                r_lb_str = f"{float(rel_interval[0]):.1%}"
                r_ub_str = f"{float(rel_interval[1]):.1%}"
                self.lbl_lisp_reliability.setText(
                    f"Execution-Reliability (S1): {rel_rate:.1%} [{r_lb_str}, {r_ub_str}]"
                )
        else:
            self.lbl_lisp_agreement.setText("Agreed Rate (95% CI): N/A (0 turns)")
            self.lbl_lisp_mcnemar.setText("Paired McNemar (b/c): N/A")
            self.lbl_lisp_reliability.setText("Execution-Reliability (S1): N/A")

    def _validate_current_rule(self) -> None:
        code = self.txt_rule_code.toPlainText().strip()
        if not code:
            self.lbl_rule_status.setText("No code to validate.")
            return

        try:
            rule_obj = self.facade.parse_rule(code)
            self.lbl_rule_status.setText(
                f"✓ Syntax valid! Parsed rule '{rule_obj.rule_id}' (Priority: {rule_obj.priority})."
            )
        except Exception as exc:
            _LOG.debug("parse_rule_failed: %s", exc)
            self.lbl_rule_status.setText(f"Syntax error: {exc}")

    def _test_eval_rule(self) -> None:
        code = self.txt_rule_code.toPlainText().strip()
        try:
            rule_obj = self.facade.parse_rule(code)
            sample_state = RuleState(
                intent="launch_app",
                entities={"app": ["calculator"]},
                apps_running=frozenset(),
                hour_local=14,
                weekday=1,
                session_turns=1,
                mode="transcript",
            )
            outcome = self.facade.evaluate_rule(rule_obj, sample_state)
            if outcome.fired and outcome.plan:
                actions_summary = ", ".join(type(a).__name__ for a in outcome.plan.actions)
                self.lbl_rule_status.setText(
                    f"✓ Evaluated rule '{rule_obj.rule_id}': Conditions matched sample state. Actions: [{actions_summary}]."
                )
            else:
                self.lbl_rule_status.setText(
                    f"✓ Evaluated rule '{rule_obj.rule_id}': Evaluation executed cleanly (preconditions did not match sample state)."
                )
        except Exception as exc:
            _LOG.debug("evaluate_rule_failed: %s", exc)
            self.lbl_rule_status.setText(f"Evaluation error: {exc}")

    def _save_selected_rule(self) -> None:
        row = self.table_lisp.currentRow()
        if row >= 0:
            item = self.table_lisp.item(row, 1)
            if item is not None:
                rule_id = item.text()
                code = self.txt_rule_code.toPlainText()
                if rule_id in self.lisp_rules:
                    self.lisp_rules[rule_id]["code"] = code
                    if self.lisp_rules[rule_id].get("on_disk"):
                        try:
                            plan_path = self.facade.save_skill_plan(rule_id, code)
                            self.lbl_rule_status.setText(
                                f"✓ Saved definition for [{rule_id}] to {plan_path}."
                            )
                        except Exception as exc:
                            _LOG.debug("save_skill_plan_failed: %s", exc)
                            self.lbl_rule_status.setText(f"✗ Save failed: {exc}")
                    else:
                        self.lbl_rule_status.setText(f"✓ Saved definition for [{rule_id}].")

    def _add_new_rule_dialog(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Add LISP Reasoning Pathway", "Enter Pathway Rule ID (e.g. custom-guard-v1):"
        )
        if ok and name:
            clean_name = name.strip()
            self.lisp_rules[clean_name] = {
                "category": "Cognitive & Temporal",
                "purpose": "Custom user-defined reasoning pathway.",
                "priority": 70,
                "state": "ACTIVE",
                "code": f'(rule "{clean_name}"\\n  :when (intent= "custom_action")\\n  :plan (say "Executing custom pathway!")\\n  :priority 70)',
            }
            self._populate_lisp_table(self.combo_lisp_cat.currentText())
            self.lbl_rule_status.setText(f"Added reasoning pathway [{clean_name}].")

    def _retire_selected_rule(self) -> None:
        row = self.table_lisp.currentRow()
        if row >= 0:
            item = self.table_lisp.item(row, 1)
            if item:
                rule_id = item.text()
                if rule_id in self.lisp_rules:
                    if self.lisp_rules[rule_id].get("on_disk"):
                        try:
                            self.facade.retire_skill(rule_id)
                        except Exception as exc:
                            _LOG.debug("retire_skill_failed: %s", exc)
                            self.lbl_rule_status.setText(f"✗ Retire failed: {exc}")
                            return
                    del self.lisp_rules[rule_id]
                    self._refresh_lisp_categories()
                    self._populate_lisp_table(self.combo_lisp_cat.currentText())
                    self.txt_rule_code.clear()
                    self.lbl_rule_status.setText(f"Retired and removed pathway [{rule_id}].")
