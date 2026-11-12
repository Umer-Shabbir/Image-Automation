from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QHBoxLayout, QMessageBox, QMenu
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from app.gui.tabs.base_tab import BaseTab
from app.core.app_state import AppState
from app.core.events import EventHub
from app.core.engine import EngineManager
from app.gui.dialogs import AccountDialog
import threading
import asyncio
import time
from automator import GoogleFlowAutomator

class AccountsTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__("Accounts", parent)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._load_accounts)

        self.btn_add = QPushButton("Add Account")
        self.btn_add.clicked.connect(self._add_account)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self._edit_account)

        self.btn_del = QPushButton("Delete")
        self.btn_del.clicked.connect(self._del_account)
        self.btn_del.setStyleSheet("background-color: #5a2a2a;")

        self.btn_reset_sleep = QPushButton("Reset Sleeping")
        self.btn_reset_sleep.setToolTip("Wake up sleeping account(s) and mark them free/idle immediately")
        self.btn_reset_sleep.clicked.connect(self._on_reset_sleeping)
        self.btn_reset_sleep.setStyleSheet("background-color: #204a6e; font-weight: bold;")

        self.btn_browser = QPushButton("Open Browser (Login)")
        self.btn_browser.clicked.connect(self._open_browser)
        self.btn_browser.setStyleSheet("background-color: #2a5a2a;")

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_del)
        btn_layout.addWidget(self.btn_reset_sleep)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_browser)
        self.layout.addLayout(btn_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Email", "Enabled", "Status", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.layout.addWidget(self.table)

        EventHub.instance().accounts_changed.connect(self._load_accounts)
        self._load_accounts()

    def _selected_account_id(self):
        rows = self.table.selectedItems()
        if not rows: return None
        return self.table.item(rows[0].row(), 0).text()

    def _load_accounts(self):
        db = AppState.instance().db
        accounts = db.get_accounts()
        now = time.time()

        self.table.setRowCount(0)
        self.table.setRowCount(len(accounts))
        for row, acct in enumerate(accounts):
            self.table.setItem(row, 0, QTableWidgetItem(str(acct.id)))
            self.table.setItem(row, 1, QTableWidgetItem(acct.name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(acct.email or ""))
            self.table.setItem(row, 3, QTableWidgetItem("Yes" if acct.enabled else "No"))

            # Status column
            is_sleeping = acct.status == "sleeping" or (acct.sleep_until and acct.sleep_until > now)
            if is_sleeping:
                rem = max(0, int((acct.sleep_until or 0.0) - now))
                if rem > 60:
                    status_text = f"sleeping ({rem // 60}m {rem % 60}s left)"
                elif rem > 0:
                    status_text = f"sleeping ({rem}s left)"
                else:
                    status_text = "sleeping"
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(QColor("#f39c12"))
            elif acct.status == "running":
                status_item = QTableWidgetItem("running")
                status_item.setForeground(QColor("#3498db"))
            elif acct.status == "idle":
                status_item = QTableWidgetItem("idle (free)")
                status_item.setForeground(QColor("#2ecc71"))
            else:
                status_item = QTableWidgetItem(acct.status or "idle")
            self.table.setItem(row, 4, status_item)

            # Action column
            if is_sleeping:
                btn_reset = QPushButton("Reset Sleep")
                btn_reset.setToolTip(f"Wake up [{acct.name}] and make it free immediately")
                btn_reset.setStyleSheet("""
                    QPushButton {
                        background-color: #1e5282;
                        color: #ffffff;
                        font-weight: bold;
                        border-radius: 3px;
                        padding: 3px 10px;
                        min-height: 22px;
                    }
                    QPushButton:hover {
                        background-color: #2a72b5;
                    }
                """)
                btn_reset.clicked.connect(lambda checked=False, aid=acct.id: self._reset_single_account(aid, show_dialog=False))
                self.table.setCellWidget(row, 5, btn_reset)
            elif acct.status == "running":
                item_act = QTableWidgetItem("Running")
                item_act.setTextAlignment(Qt.AlignCenter)
                item_act.setForeground(QColor("#7f8c8d"))
                self.table.setItem(row, 5, item_act)
            else:
                item_act = QTableWidgetItem("Free")
                item_act.setTextAlignment(Qt.AlignCenter)
                item_act.setForeground(QColor("#7f8c8d"))
                self.table.setItem(row, 5, item_act)

    def _reset_single_account(self, account_id: str, show_dialog: bool = True):
        if not account_id:
            return
        accounts = AppState.instance().db.get_accounts()
        acct = next((a for a in accounts if a.id == account_id), None)
        if not acct:
            return

        if acct.status == "running":
            QMessageBox.warning(self, "Account Busy", f"Account '{acct.name}' is currently running. Stop workers before resetting.")
            return

        EngineManager.instance().reset_account_sleep(account_id)
        self._load_accounts()
        if show_dialog:
            QMessageBox.information(self, "Account Free", f"Account '{acct.name}' sleep has been reset.\nStatus is now Free / Idle.")

    def _on_reset_sleeping(self):
        acct_id = self._selected_account_id()
        accounts = AppState.instance().db.get_accounts()
        now = time.time()

        if acct_id:
            acct = next((a for a in accounts if a.id == acct_id), None)
            if acct:
                if acct.status == "sleeping" or (acct.sleep_until and acct.sleep_until > now):
                    self._reset_single_account(acct.id)
                    return
                elif acct.status != "running":
                    reply = QMessageBox.question(
                        self,
                        "Reset Account Status",
                        f"Account '{acct.name}' is currently '{acct.status}'. Reset status to free/idle anyway?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.Yes:
                        self._reset_single_account(acct.id)
                    return
                else:
                    self._reset_single_account(acct.id)
                    return

        # No account selected: check for all sleeping accounts
        sleeping = [a for a in accounts if a.status == "sleeping" or (a.sleep_until and a.sleep_until > now)]
        if not sleeping:
            QMessageBox.information(
                self,
                "Reset Sleeping",
                "No accounts are currently sleeping.\nSelect an account from the list to reset it to free."
            )
            return

        names = "\n".join(f"• {a.name} ({a.email or a.id})" for a in sleeping[:5])
        if len(sleeping) > 5:
            names += f"\n... and {len(sleeping) - 5} more"

        reply = QMessageBox.question(
            self,
            "Reset Sleeping Accounts",
            f"Found {len(sleeping)} sleeping account(s):\n\n{names}\n\nReset sleeping to make them free?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            count = EngineManager.instance().reset_all_sleeping_accounts()
            self._load_accounts()
            QMessageBox.information(self, "Accounts Free", f"Successfully reset {count} account(s) to free/idle.")

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        acct_id = id_item.text()
        accounts = AppState.instance().db.get_accounts()
        acct = next((a for a in accounts if a.id == acct_id), None)
        if not acct:
            return

        menu = QMenu(self)
        act_reset = menu.addAction(f"Reset Sleeping for '{acct.name}' (Make Free)")
        menu.addSeparator()
        act_browser = menu.addAction("Open Browser (Login)")
        act_edit = menu.addAction("Edit Account")
        act_del = menu.addAction("Delete Account")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == act_reset:
            self._reset_single_account(acct_id)
        elif action == act_browser:
            self._open_browser(acct_id)
        elif action == act_edit:
            self._edit_account(acct_id)
        elif action == act_del:
            self._del_account(acct_id)

    def _add_account(self):
        d = AccountDialog(parent=self)
        if d.exec():
            AppState.instance().db.save_account(d.get_account())
            self._load_accounts()

    def _edit_account(self, acct_id=None):
        if not acct_id:
            acct_id = self._selected_account_id()
        if not acct_id: return
        accounts = AppState.instance().db.get_accounts()
        acct = next((a for a in accounts if a.id == acct_id), None)
        if not acct: return

        d = AccountDialog(account=acct, parent=self)
        if d.exec():
            AppState.instance().db.save_account(d.get_account())
            self._load_accounts()

    def _del_account(self, acct_id=None):
        if not acct_id:
            acct_id = self._selected_account_id()
        if not acct_id: return
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete account {acct_id}?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            AppState.instance().db.delete_account(acct_id)
            self._load_accounts()

    def _open_browser(self, acct_id=None):
        if not acct_id:
            acct_id = self._selected_account_id()
        if not acct_id:
            QMessageBox.warning(self, "No Selection", "Please select an account first.")
            return

        def _launch():
            async def _run():
                from copy import deepcopy
                settings = AppState.instance().db.get_settings()
                s = deepcopy(settings)
                setattr(s, 'headless', False)

                auto = GoogleFlowAutomator(profile_dir=f"profiles/{acct_id}", settings=s)

                await auto.start()
                print(f"[{acct_id}] Browser launched for manual login. Waiting...")
                await asyncio.sleep(300)
                await auto.stop()
            try:
                asyncio.run(_run())
            except Exception as e:
                import traceback
                traceback.print_exc()
                print("Browser closed:", e)

        QMessageBox.information(self, "Launching", "Opening a browser window for manual login. You have 5 minutes before it auto-closes.")
        threading.Thread(target=_launch, daemon=True).start()