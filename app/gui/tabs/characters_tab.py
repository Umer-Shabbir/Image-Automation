from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QHBoxLayout, QMessageBox
from app.gui.tabs.base_tab import BaseTab
from app.core.app_state import AppState
from app.core.events import EventHub
from app.gui.dialogs import CharacterDialog

class CharactersTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__("Characters", parent)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._load)

        self.btn_add = QPushButton("Add Character")
        self.btn_add.clicked.connect(self._add_char)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self._edit_char)

        self.btn_del = QPushButton("Delete")
        self.btn_del.clicked.connect(self._del_char)
        self.btn_del.setStyleSheet("background-color: #5a2a2a;")

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_del)
        btn_layout.addStretch()
        self.layout.addLayout(btn_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Prompt Tag", "Active"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.layout.addWidget(self.table)

        EventHub.instance().characters_changed.connect(self._load)
        self._load()

    def _selected_id(self):
        rows = self.table.selectedItems()
        if not rows: return None
        return self.table.item(rows[0].row(), 0).text()

    def _load(self):
        db = AppState.instance().db
        chars = db.get_characters()

        self.table.setRowCount(0)
        self.table.setRowCount(len(chars))
        for row, c in enumerate(chars):
            self.table.setItem(row, 0, QTableWidgetItem(str(c.id)))
            self.table.setItem(row, 1, QTableWidgetItem(c.name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(c.prompt_tag or ""))
            self.table.setItem(row, 3, QTableWidgetItem("Yes" if c.is_active else "No"))

    def _add_char(self):
        d = CharacterDialog(parent=self)
        if d.exec():
            AppState.instance().db.save_character(d.get_character())
            EventHub.instance().characters_changed.emit()

    def _edit_char(self):
        cid = self._selected_id()
        if not cid: return
        chars = AppState.instance().db.get_characters()
        char = next((c for c in chars if c.id == cid), None)
        if not char: return

        d = CharacterDialog(char=char, parent=self)
        if d.exec():
            AppState.instance().db.save_character(d.get_character())
            EventHub.instance().characters_changed.emit()

    def _del_char(self):
        cid = self._selected_id()
        if not cid: return
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete character?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            AppState.instance().db.delete_character(cid)
            EventHub.instance().characters_changed.emit()