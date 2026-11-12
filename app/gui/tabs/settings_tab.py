from PySide6.QtWidgets import QFormLayout, QLineEdit, QSpinBox, QPushButton, QWidget, QCheckBox, QScrollArea, QComboBox
from app.gui.tabs.base_tab import BaseTab
from app.core.app_state import AppState

class SettingsTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__("Settings", parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")

        self.form_widget = QWidget()
        self.form_layout = QFormLayout(self.form_widget)

        # ── Platform Selection ────────────────────────────────────────────────
        self.val_platform = QComboBox()
        self.val_platform.addItem("Google Flow", "flow")
        self.val_platform.addItem("Gemini Bulk App", "bulk_app")
        self.form_layout.addRow("Generation Platform:", self.val_platform)

        self.val_bulk_app_url = QLineEdit()
        self.form_layout.addRow("Bulk App URL:", self.val_bulk_app_url)

        self.val_flow_url = QLineEdit()
        self.form_layout.addRow("Flow URL:", self.val_flow_url)

        self.val_bulk_batch_size = QSpinBox()
        self.val_bulk_batch_size.setRange(1, 1000)
        self.form_layout.addRow("Bulk Batch Size:", self.val_bulk_batch_size)

        # ── Parallelism & Limits ──────────────────────────────────────────────
        self.val_parallel = QSpinBox()
        self.val_parallel.setRange(1, 100)
        self.form_layout.addRow("Max Parallel Accounts:", self.val_parallel)

        self.val_hard_limit = QSpinBox()
        self.val_hard_limit.setRange(0, 100000)
        self.val_hard_limit.setSpecialValueText("Disabled")
        self.form_layout.addRow("Hard Generation Limit:", self.val_hard_limit)

        self.val_output = QLineEdit()
        self.form_layout.addRow("Output Directory:", self.val_output)

        self.val_type_wpm = QSpinBox()
        self.val_type_wpm.setRange(10, 1000)
        self.form_layout.addRow("Typewriter Speed (WPM):", self.val_type_wpm)

        self.val_delay_min = QSpinBox()
        self.val_delay_min.setRange(0, 1000)
        self.val_delay_max = QSpinBox()
        self.val_delay_max.setRange(0, 1000)
        self.form_layout.addRow("Prompt Delay Min/Max (s):", self._horiz_spinbox(self.val_delay_min, self.val_delay_max))

        self.val_refresh_threshold = QSpinBox()
        self.val_refresh_threshold.setRange(0, 1000)
        self.val_refresh_threshold.setSpecialValueText("Disabled")
        self.form_layout.addRow("Project Refresh (Gens):", self.val_refresh_threshold)

        self.chk_stealth = QCheckBox("Enable Stealth")
        self.form_layout.addRow("Stealth Mode:", self.chk_stealth)

        scroll.setWidget(self.form_widget)
        self.layout.addWidget(scroll)

        self.btn_save = QPushButton("Save Settings")
        self.btn_save.clicked.connect(self._save)
        self.layout.addWidget(self.btn_save)

        self._load()

    def _horiz_spinbox(self, sb1, sb2):
        from PySide6.QtWidgets import QHBoxLayout
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0,0,0,0)
        l.addWidget(sb1)
        l.addWidget(sb2)
        return w

    def _load(self):
        s = AppState.instance().db.get_settings()
        plat = getattr(s, "generation_platform", "flow") or "flow"
        idx = self.val_platform.findData(plat)
        if idx >= 0:
            self.val_platform.setCurrentIndex(idx)
        self.val_bulk_app_url.setText(getattr(s, "bulk_app_url", "https://gemini.google.com/share/79e5de5150e6") or "")
        self.val_bulk_batch_size.setValue(getattr(s, "bulk_batch_size", 10) or 10)
        self.val_parallel.setValue(s.max_parallel_accounts)
        self.val_hard_limit.setValue(getattr(s, "hard_generation_limit", 0) or 0)
        self.val_output.setText(s.output_dir or "")
        self.val_flow_url.setText(s.flow_url or "")
        self.val_type_wpm.setValue(s.type_wpm)
        self.val_delay_min.setValue(s.delay_between_prompts)
        self.val_delay_max.setValue(s.delay_between_prompts)
        self.val_refresh_threshold.setValue(getattr(s, "project_refresh_threshold", 20))
        self.chk_stealth.setChecked(s.enable_validation)

    def _save(self):
        db = AppState.instance().db
        s = db.get_settings()
        s.generation_platform = self.val_platform.currentData()
        s.bulk_app_url = self.val_bulk_app_url.text().strip()
        s.bulk_batch_size = self.val_bulk_batch_size.value()
        s.max_parallel_accounts = self.val_parallel.value()
        s.hard_generation_limit = self.val_hard_limit.value()
        s.output_dir = self.val_output.text()
        s.flow_url = self.val_flow_url.text()
        s.type_wpm = self.val_type_wpm.value()
        s.delay_between_prompts = self.val_delay_min.value()
        s.project_refresh_threshold = self.val_refresh_threshold.value()
        s.enable_validation = self.chk_stealth.isChecked()
        db.save_settings(s)