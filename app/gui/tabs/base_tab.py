from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class BaseTab(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)

        lbl = QLabel(title)
        lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff; padding-bottom: 20px;")
        self.layout.addWidget(lbl)