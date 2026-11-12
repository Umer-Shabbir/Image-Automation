from PySide6.QtWidgets import QTextEdit
from app.gui.tabs.base_tab import BaseTab
from app.core.events import EventHub
from datetime import datetime

class LogsTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__("Logs", parent)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("font-family: Consolas, monospace; background-color: #1e1e32; color: #e8e8f0; padding: 10px;")
        self.layout.addWidget(self.log_area)

        EventHub.instance().log_emitted.connect(self._on_log)

    def _on_log(self, account_id: str, message: str, level: str, timestamp: float):
        dt = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        prefix = f"[{dt}]"
        if account_id:
            prefix += f" [{account_id[:8]}]"

        color = "#e8e8f0"
        if level == "error":
            color = "#ff6b6b"
        elif level == "warning" or level == "warn":
            color = "#ffd93d"

        line = f'<span style="color: {color};">{prefix} {message}</span>'
        self.log_area.append(line)