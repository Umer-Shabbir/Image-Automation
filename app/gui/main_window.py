from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget
from app.gui.components.sidebar import Sidebar

from app.gui.tabs.dashboard_tab import DashboardTab
from app.gui.tabs.queue_tab import QueueTab
from app.gui.tabs.accounts_tab import AccountsTab
from app.gui.tabs.characters_tab import CharactersTab
from app.gui.tabs.settings_tab import SettingsTab
from app.gui.tabs.logs_tab import LogsTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Automation Batch Pro")
        self.resize(1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # Initialize tabs
        self.tabs = [
            DashboardTab(),
            QueueTab(),
            AccountsTab(),
            CharactersTab(),
            SettingsTab(),
            LogsTab()
        ]

        for tab in self.tabs:
            self.stack.addWidget(tab)

        self.sidebar.tab_selected.connect(self.stack.setCurrentIndex)