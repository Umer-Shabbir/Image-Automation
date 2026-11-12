from PySide6.QtWidgets import QHBoxLayout, QPushButton, QLabel, QGridLayout
from PySide6.QtCore import Qt
from app.gui.tabs.base_tab import BaseTab
from app.core.engine import EngineManager
from app.core.events import EventHub
from app.core.app_state import AppState

class DashboardTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__("Dashboard", parent)

        # Controls
        controls = QHBoxLayout()
        self.btn_start = QPushButton("Start Workers")
        self.btn_stop = QPushButton("Stop Workers")
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")

        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_resume.clicked.connect(self._on_resume)

        for b in [self.btn_start, self.btn_stop, self.btn_pause, self.btn_resume]:
            controls.addWidget(b)

        self.layout.addLayout(controls)

        # Status
        self.lbl_status = QLabel("Engine: Stopped")
        self.lbl_status.setStyleSheet("font-size: 16px; margin-top: 10px;")
        self.layout.addWidget(self.lbl_status)

        # Stats Grid
        self.stats_grid = QGridLayout()
        self.lbl_total = QLabel("Total: 0")
        self.lbl_done = QLabel("Done: 0")
        self.lbl_failed = QLabel("Failed: 0")
        self.lbl_pending = QLabel("Pending: 0")

        self.stats_grid.addWidget(self.lbl_total, 0, 0)
        self.stats_grid.addWidget(self.lbl_done, 0, 1)
        self.stats_grid.addWidget(self.lbl_failed, 1, 0)
        self.stats_grid.addWidget(self.lbl_pending, 1, 1)
        self.layout.addLayout(self.stats_grid)
        self.layout.addStretch()

        # Connections
        EventHub.instance().engine_state_changed.connect(self._on_engine_state)
        EventHub.instance().queue_stats_updated.connect(self._on_stats_updated)

        self._refresh()

    def _refresh(self):
        stats = AppState.instance().queue_mgr.stats()
        self._on_stats_updated(stats)

    def _on_start(self):
        EngineManager.instance().start_batch()

    def _on_stop(self):
        EngineManager.instance().stop_batch()

    def _on_pause(self):
        EngineManager.instance().pause_batch()

    def _on_resume(self):
        EngineManager.instance().resume_batch()

    def _on_engine_state(self, is_running: bool):
        self.lbl_status.setText(f"Engine: {'Running' if is_running else 'Stopped'}")

    def _on_stats_updated(self, stats: dict):
        self.lbl_total.setText(f"Total: {stats.get('total', 0)}")
        self.lbl_done.setText(f"Done: {stats.get('done', 0)}")
        self.lbl_failed.setText(f"Failed: {stats.get('failed', 0)}")
        self.lbl_pending.setText(f"Pending: {stats.get('pending', 0)}")