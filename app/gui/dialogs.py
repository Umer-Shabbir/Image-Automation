import os
import json
import asyncio
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox, 
    QPushButton, QFormLayout, QTextEdit, QMessageBox, QFileDialog, QSpinBox
)
from PySide6.QtCore import Qt
from app.core.app_state import AppState
from models import Account, Character, Job

class AccountDialog(QDialog):
    def __init__(self, account=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Account" if account else "Add Account")
        self.setMinimumWidth(400)
        self.account = account or Account()
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.val_name = QLineEdit(self.account.name)
        self.val_email = QLineEdit(self.account.email)
        self.val_password = QLineEdit(self.account.password)
        self.chk_enabled = QCheckBox()
        self.chk_enabled.setChecked(self.account.enabled)
        
        form.addRow("Name:", self.val_name)
        form.addRow("Email:", self.val_email)
        form.addRow("Password:", self.val_password)
        form.addRow("Enabled:", self.chk_enabled)
        
        layout.addLayout(form)
        
        # Buttons
        btns = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btn_save.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)
        layout.addStretch()
        layout.addLayout(btns)
        
    def get_account(self) -> Account:
        """Returns the updated account model"""
        self.account.name = self.val_name.text().strip()
        self.account.email = self.val_email.text().strip()
        self.account.password = self.val_password.text().strip()
        self.account.enabled = self.chk_enabled.isChecked()
        return self.account


class CharacterDialog(QDialog):
    def __init__(self, char=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Character" if char else "Add Character")
        self.setMinimumWidth(500)
        self.char = char or Character()
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.val_name = QLineEdit(self.char.name)
        self.val_tag = QLineEdit(self.char.prompt_tag)
        self.val_desc = QTextEdit(self.char.description)
        self.chk_active = QCheckBox()
        self.chk_active.setChecked(self.char.is_active)
        
        form.addRow("Name:", self.val_name)
        form.addRow("Prompt Tag:", self.val_tag)
        form.addRow("Description:", self.val_desc)
        form.addRow("Active:", self.chk_active)
        
        layout.addLayout(form)
        
        btns = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btn_save.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)
        layout.addStretch()
        layout.addLayout(btns)
        
    def get_character(self) -> Character:
        self.char.name = self.val_name.text().strip()
        self.char.prompt_tag = self.val_tag.text().strip()
        self.char.description = self.val_desc.toPlainText().strip()
        self.char.is_active = self.chk_active.isChecked()
        return self.char


class AddScriptDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Raw Script / Jobs")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Paste Raw Script Output lines (one prompt per line):"))
        
        self.val_topic = QLineEdit()
        self.val_topic.setPlaceholderText("Topic Name (e.g. History Facts)")
        
        self.val_text = QTextEdit()
        
        layout.addWidget(self.val_topic)
        layout.addWidget(self.val_text)
        
        btns = QHBoxLayout()
        btn_add = QPushButton("Add to Queue")
        btn_cancel = QPushButton("Cancel")
        btn_add.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_add)
        layout.addLayout(btns)

    def get_jobs(self):
        text = self.val_text.toPlainText().strip()
        topic = self.val_topic.text().strip()
        if not text or not topic:
            return []
            
        jobs = []
        for i, line in enumerate(text.split("\n")):
            line = line.strip()
            if line:
                j = Job(
                    topic_name=topic,
                    topic_slug=topic.replace(" ", "_").lower(),
                    prompt_text=line,
                    prompt_index=i+1,
                )
                jobs.append(j)
        return jobs
