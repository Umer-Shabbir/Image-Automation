from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt

class Sidebar(QWidget):
    tab_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        title = QLabel("Batch Pro")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #6c63ff; padding: 20px 10px;")
        layout.addWidget(title)

        self.buttons = []
        tabs = ["Dashboard", "Queue", "Accounts", "Characters", "Settings", "Logs"]

        for idx, text in enumerate(tabs):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 12px 20px;
                    border: none;
                    background: transparent;
                    color: #e8e8f0;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #1e1e32;
                    border-radius: 4px;
                }
                QPushButton:checked {
                    background: #6c63ff;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            btn.clicked.connect(lambda checked, i=idx: self._on_btn_clicked(i))
            self.buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        if self.buttons:
            self.buttons[0].setChecked(True)

    def _on_btn_clicked(self, index: int):
        for i, btn in enumerate(self.buttons):
            if i != index:
                btn.setChecked(False)
            else:
                btn.setChecked(True)
        self.tab_selected.emit(index)