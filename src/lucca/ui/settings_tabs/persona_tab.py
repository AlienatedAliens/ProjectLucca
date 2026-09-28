"""
Project Lucca — Persona & Archetypes Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lucca.brain.prompt_builder import (
    ARCHETYPES,
    compile_trait_modulators,
    preview_system_prompt,
)
from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade


class PersonaTab(QWidget):
    """Tab 0: Persona & Archetypes (Lossless TOML, Prose Compilation)."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self._build_ui()

    @property
    def user_archetypes(self) -> dict[str, str]:
        return getattr(self.dialog, "user_archetypes", {})

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Archetype & Formality Selection
        grp_arch = QGroupBox("Persona Archetype & Inflection Mode", self)
        f_arch = QFormLayout(grp_arch)

        h_arch_sel = QHBoxLayout()
        self.combo_archetype = QComboBox(grp_arch)
        self._repopulate_archetypes_combo()
        h_arch_sel.addWidget(self.combo_archetype, stretch=3)

        self.btn_add_arch = QPushButton("➕ New Archetype", grp_arch)
        self.btn_add_arch.clicked.connect(self._add_custom_archetype)
        h_arch_sel.addWidget(self.btn_add_arch)

        self.btn_del_arch = QPushButton("🗑️ Delete", grp_arch)
        self.btn_del_arch.clicked.connect(self._delete_custom_archetype)
        h_arch_sel.addWidget(self.btn_del_arch)

        self.combo_archetype.currentIndexChanged.connect(self._on_archetype_changed)
        f_arch.addRow("Active Archetype:", h_arch_sel)

        self.combo_formality = QComboBox(grp_arch)
        self.combo_formality.addItem("Casual (Friendly, colloquial partner dialogue)", "casual")
        self.combo_formality.addItem("Neutral (Balanced, direct assistant phrasing)", "neutral")
        self.combo_formality.addItem("Precise (High technical rigor, concise)", "precise")
        idx_f = self.combo_formality.findData(getattr(self.dialog, "current_formality", "casual"))
        if idx_f >= 0:
            self.combo_formality.setCurrentIndex(idx_f)
        self.combo_formality.currentIndexChanged.connect(self._update_prompt_preview)
        f_arch.addRow("Conversational Formality:", self.combo_formality)

        layout.addWidget(grp_arch)

        # Behavior & Boundaries
        grp_bound = QGroupBox("Behavior & Boundaries", self)
        f_bound = QFormLayout(grp_bound)

        self.chk_uses_name = QCheckBox("Address creator by name ('Lucca')", grp_bound)
        self.chk_uses_name.setChecked(getattr(self.dialog, "current_uses_name", True))
        self.chk_uses_name.toggled.connect(self._update_prompt_preview)
        f_bound.addRow("Identity & Name:", self.chk_uses_name)

        self.chk_admits_uncertainty = QCheckBox(
            "Admit uncertainty aloud ('I\\'m not sure' vs hallucinating)", grp_bound
        )
        self.chk_admits_uncertainty.setChecked(getattr(self.dialog, "current_admits_uncertainty", True))
        self.chk_admits_uncertainty.toggled.connect(self._update_prompt_preview)
        f_bound.addRow("Truthfulness:", self.chk_admits_uncertainty)

        self.chk_never_pretend = QCheckBox(
            "Never simulate biological emotion (describe affect as system state)", grp_bound
        )
        self.chk_never_pretend.setChecked(getattr(self.dialog, "current_never_pretend", True))
        self.chk_never_pretend.toggled.connect(self._update_prompt_preview)
        f_bound.addRow("Affect Substrate:", self.chk_never_pretend)

        self.line_refuse_topics = QLineEdit(grp_bound)
        self.line_refuse_topics.setPlaceholderText(
            "e.g. medical diagnosis, financial advice, unauthorized execution (comma-separated)"
        )
        refuse_topics = getattr(self.dialog, "current_refuse_topics", [])
        self.line_refuse_topics.setText(", ".join(refuse_topics))
        self.line_refuse_topics.textChanged.connect(self._update_prompt_preview)
        f_bound.addRow("Declined Topics:", self.line_refuse_topics)

        layout.addWidget(grp_bound)

        # Affect Engine (Read/Write [affect] in persona.toml)
        grp_affect = QGroupBox("Affect Engine (Dynamic Emotional State Decay)", self)
        f_affect = QFormLayout(grp_affect)

        self.chk_affect_enabled = QCheckBox("Enable dynamic affect state tracking", grp_affect)
        self.chk_affect_enabled.setChecked(getattr(self.dialog, "current_affect_enabled", True))
        f_affect.addRow("Affect Tracking:", self.chk_affect_enabled)

        h_decay = QHBoxLayout()
        self.slider_affect_decay = QSlider(Qt.Orientation.Horizontal, grp_affect)
        self.slider_affect_decay.setRange(60, 1800)
        self.slider_affect_decay.setSingleStep(30)
        decay_val = getattr(self.dialog, "current_decay_tau", 300.0)
        self.slider_affect_decay.setValue(int(decay_val))
        decay_init_s = int(decay_val)
        decay_init_m = decay_val / 60.0
        self.lbl_affect_decay = QLabel(f"{decay_init_s}s ({decay_init_m:.1f}m)", grp_affect)
        self.lbl_affect_decay.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_affect_decay.valueChanged.connect(
            lambda v: self.lbl_affect_decay.setText(f"{v}s ({v / 60.0:.1f}m)")
        )
        h_decay.addWidget(self.slider_affect_decay)
        h_decay.addWidget(self.lbl_affect_decay)
        f_affect.addRow("Half-Life (tau):", h_decay)

        h_delta = QHBoxLayout()
        self.slider_affect_delta = QSlider(Qt.Orientation.Horizontal, grp_affect)
        self.slider_affect_delta.setRange(0, 25)
        delta_val = getattr(self.dialog, "current_max_speed_delta", 0.08)
        self.slider_affect_delta.setValue(int(delta_val * 100))
        delta_init = int(delta_val * 100)
        self.lbl_affect_delta = QLabel(f"±{delta_init}%", grp_affect)
        self.lbl_affect_delta.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_affect_delta.valueChanged.connect(
            lambda v: self.lbl_affect_delta.setText(f"±{v}%")
        )
        h_delta.addWidget(self.slider_affect_delta)
        h_delta.addWidget(self.lbl_affect_delta)
        f_affect.addRow("Max Speed Delta:", h_delta)

        layout.addWidget(grp_affect)

        # Granular Trait Modulators (Prose Compilation)
        grp_traits = QGroupBox("Granular Trait Modulators (Compiled to Natural Prose)", self)
        f_traits = QFormLayout(grp_traits)

        # Tech Depth
        h_td = QHBoxLayout()
        self.slider_tech = QSlider(Qt.Orientation.Horizontal, grp_traits)
        self.slider_tech.setRange(0, 100)
        tech_val = getattr(self.dialog, "current_tech_depth", 0.8)
        self.slider_tech.setValue(int(tech_val * 100))
        self.lbl_tech_val = QLabel(f"{tech_val:.2f}", grp_traits)
        self.lbl_tech_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_tech.valueChanged.connect(self._on_traits_changed)
        h_td.addWidget(self.slider_tech)
        h_td.addWidget(self.lbl_tech_val)
        f_traits.addRow("Technical Depth:", h_td)

        # Warmth
        h_wm = QHBoxLayout()
        self.slider_warmth = QSlider(Qt.Orientation.Horizontal, grp_traits)
        self.slider_warmth.setRange(0, 100)
        warmth_val = getattr(self.dialog, "current_warmth", 0.7)
        self.slider_warmth.setValue(int(warmth_val * 100))
        self.lbl_warmth_val = QLabel(f"{warmth_val:.2f}", grp_traits)
        self.lbl_warmth_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_warmth.valueChanged.connect(self._on_traits_changed)
        h_wm.addWidget(self.slider_warmth)
        h_wm.addWidget(self.lbl_warmth_val)
        f_traits.addRow("Warmth / Playfulness:", h_wm)

        # Directness
        h_dr = QHBoxLayout()
        self.slider_directness = QSlider(Qt.Orientation.Horizontal, grp_traits)
        self.slider_directness.setRange(0, 100)
        direct_val = getattr(self.dialog, "current_directness", 0.7)
        self.slider_directness.setValue(int(direct_val * 100))
        self.lbl_directness_val = QLabel(f"{direct_val:.2f}", grp_traits)
        self.lbl_directness_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_directness.valueChanged.connect(self._on_traits_changed)
        h_dr.addWidget(self.slider_directness)
        h_dr.addWidget(self.lbl_directness_val)
        f_traits.addRow("Directness:", h_dr)

        self.lbl_compiled_traits = QLabel(grp_traits)
        self.lbl_compiled_traits.setFont(QFont("Consolas", 8))
        self.lbl_compiled_traits.setStyleSheet("color: #a0aec0; font-style: italic;")
        self.lbl_compiled_traits.setWordWrap(True)
        f_traits.addRow("Compiled Prose:", self.lbl_compiled_traits)

        layout.addWidget(grp_traits)

        # Custom Prompt Directives & Live Preview
        grp_prompt = QGroupBox(
            "Custom Persona Directives (Additive) & Live System Prompt Preview", self
        )
        v_prompt = QVBoxLayout(grp_prompt)

        self.txt_custom_prompt = QPlainTextEdit(grp_prompt)
        self.txt_custom_prompt.setPlaceholderText(
            "Enter optional custom persona directives here (compiled additively)..."
        )
        self.txt_custom_prompt.setPlainText(getattr(self.dialog, "current_custom_prompt", ""))
        self.txt_custom_prompt.setMaximumHeight(80)
        self.txt_custom_prompt.textChanged.connect(self._update_prompt_preview)
        v_prompt.addWidget(self.txt_custom_prompt)

        h_pv_hdr = QHBoxLayout()
        h_pv_hdr.addWidget(
            QLabel("Full Compiled System Prompt (with Architecture & Tools):", grp_prompt)
        )
        h_pv_hdr.addStretch()
        self.lbl_token_count = QLabel("Approx: -- tokens", grp_prompt)
        self.lbl_token_count.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        h_pv_hdr.addWidget(self.lbl_token_count)
        v_prompt.addLayout(h_pv_hdr)

        self.txt_preview = QPlainTextEdit(grp_prompt)
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setMaximumHeight(140)
        self.txt_preview.setFont(QFont("Consolas", 8))
        v_prompt.addWidget(self.txt_preview)

        layout.addWidget(grp_prompt)
        self._on_traits_changed()

    def _repopulate_archetypes_combo(self) -> None:
        self.combo_archetype.blockSignals(True)
        self.combo_archetype.clear()
        self.combo_archetype.addItem("Inventor (Technical, Enthusiastic Companion)", "inventor")
        self.combo_archetype.addItem("Genki (Energetic, Cheerful Partner)", "genki")
        self.combo_archetype.addItem("Kuudere (Quiet, Hyper-Competent Analytical)", "kuudere")

        user_arch = getattr(self.dialog, "user_archetypes", {})
        for name in sorted(user_arch.keys()):
            self.combo_archetype.addItem(f"Custom: {name}", name)

        current_arch = getattr(self.dialog, "current_archetype", "inventor")
        idx = self.combo_archetype.findData(current_arch)
        if idx >= 0:
            self.combo_archetype.setCurrentIndex(idx)
        else:
            self.combo_archetype.setCurrentIndex(0)
        self.combo_archetype.blockSignals(False)

    def _on_archetype_changed(self) -> None:
        arch = str(self.combo_archetype.currentData())
        user_arch = getattr(self.dialog, "user_archetypes", {})
        is_custom = arch in user_arch
        self.btn_del_arch.setEnabled(is_custom)
        self._update_prompt_preview()

    def _add_custom_archetype(self) -> None:
        name, ok = QInputDialog.getText(self, "New Custom Archetype", "Enter archetype identifier:")
        if not ok or not name.strip():
            return
        clean_name = name.strip().lower().replace(" ", "_")
        user_arch = getattr(self.dialog, "user_archetypes", {})
        if clean_name in ARCHETYPES or clean_name in user_arch:
            QMessageBox.warning(
                self, "Archetype Exists", f"Archetype '{clean_name}' already exists."
            )
            return

        desc, ok_desc = QInputDialog.getMultiLineText(
            self,
            "Archetype Voice & Prose",
            "Enter hybrid prose (3-4 bulleted facts + voice paragraph, <= 120 tokens):",
            "• Specialized technical or conversational focus\n• Direct, expressive delivery\n\nReady to proceed!",
        )
        if not ok_desc or not desc.strip():
            return

        user_arch[clean_name] = desc.strip()
        self.dialog.user_archetypes = user_arch
        self.dialog.current_archetype = clean_name
        self._repopulate_archetypes_combo()
        self._update_prompt_preview()

    def _delete_custom_archetype(self) -> None:
        arch = str(self.combo_archetype.currentData())
        user_arch = getattr(self.dialog, "user_archetypes", {})
        if arch not in user_arch:
            QMessageBox.information(
                self, "Built-in Archetype", "Built-in archetypes cannot be deleted."
            )
            return
        del user_arch[arch]
        self.dialog.user_archetypes = user_arch
        self.dialog.current_archetype = "inventor"
        self._repopulate_archetypes_combo()
        self._update_prompt_preview()

    def _on_traits_changed(self) -> None:
        td = self.slider_tech.value() / 100.0
        wm = self.slider_warmth.value() / 100.0
        dr = self.slider_directness.value() / 100.0

        self.lbl_tech_val.setText(f"{td:.2f}")
        self.lbl_warmth_val.setText(f"{wm:.2f}")
        self.lbl_directness_val.setText(f"{dr:.2f}")

        compiled = compile_trait_modulators(td, wm, dr)
        if compiled:
            self.lbl_compiled_traits.setText(f'"{compiled}"')
        else:
            self.lbl_compiled_traits.setText(
                "(Neutral default 0.5 — no additional prompt directives emitted)"
            )

        self._update_prompt_preview()

    def _update_prompt_preview(self) -> None:
        arch = str(self.combo_archetype.currentData())
        form = str(self.combo_formality.currentData())
        custom = self.txt_custom_prompt.toPlainText().strip()
        td = self.slider_tech.value() / 100.0
        wm = self.slider_warmth.value() / 100.0
        dr = self.slider_directness.value() / 100.0
        uses_name = self.chk_uses_name.isChecked()
        admits_unc = self.chk_admits_uncertainty.isChecked()
        never_pret = self.chk_never_pretend.isChecked()

        raw_refuse = self.line_refuse_topics.text().strip()
        refuse_list = [r.strip() for r in raw_refuse.split(",") if r.strip()]

        user_arch = getattr(self.dialog, "user_archetypes", {})
        full_prompt = preview_system_prompt(
            archetype=arch,
            formality=form,
            custom_prompt=custom,
            technical_depth=td,
            warmth=wm,
            directness=dr,
            uses_your_name=uses_name,
            admits_uncertainty=admits_unc,
            never_pretend_to_feel=never_pret,
            refuse_topics=refuse_list,
            user_archetypes=user_arch,
        )
        self.txt_preview.setPlainText(full_prompt)

        n_chars = len(full_prompt)
        n_tokens = max(1, int(n_chars / 4))
        self.lbl_token_count.setText(f"Approx: ~{n_tokens} tokens ({n_chars} chars)")
