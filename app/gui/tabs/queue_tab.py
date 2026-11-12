from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QHBoxLayout, QMessageBox, QFileDialog
import os
import json
from pathlib import Path
from app.gui.tabs.base_tab import BaseTab
from app.core.app_state import AppState
from app.core.events import EventHub
from app.gui.dialogs import AddScriptDialog
from models import Job

class QueueTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__("Queue", parent)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._load_jobs)

        self.btn_add = QPushButton("Add Raw Script")
        self.btn_add.clicked.connect(self._on_add_script)

        self.btn_scan = QPushButton("Directory Scan")
        self.btn_scan.clicked.connect(self._on_scan_dir)

        self.btn_clear = QPushButton("Clear Queue")
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_clear.setStyleSheet("background-color: #5a2a2a;")

        self.btn_retry = QPushButton("Retry Failed")
        self.btn_retry.clicked.connect(self._on_retry)

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_scan)
        btn_layout.addWidget(self.btn_retry)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_clear)
        self.layout.addLayout(btn_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Topic", "Prompt", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layout.addWidget(self.table)

        EventHub.instance().queue_changed.connect(self._load_jobs)
        self._load_jobs()

    def _load_jobs(self):
        db = AppState.instance().db
        jobs = db.get_jobs()
        # limit to recent 500 for UI responsiveness
        jobs = list(reversed(jobs))[:500]

        self.table.setRowCount(0)
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            self.table.setItem(row, 0, QTableWidgetItem(str(job.id)))
            self.table.setItem(row, 1, QTableWidgetItem(job.topic_name or ""))
            p_text = (job.prompt_text or "").replace('\n', ' ')
            self.table.setItem(row, 2, QTableWidgetItem(p_text[:70] + ("..." if len(p_text)>70 else "")))
            self.table.setItem(row, 3, QTableWidgetItem(job.status or "pending"))

    def _on_add_script(self):
        d = AddScriptDialog(parent=self)
        if d.exec():
            jobs = d.get_jobs()
            if jobs:
                AppState.instance().queue_mgr.add_jobs(jobs)
                EventHub.instance().queue_changed.emit()

    @staticmethod
    def extract_thumbnail_prompts(folder: Path, data: dict = None) -> list[str]:
        import re
        data = data or {}
        thumb_prompts = []

        # 1. Primary: structured thumbnail_prompts in project.json / metadata.json
        if "thumbnail_prompts" in data and isinstance(data["thumbnail_prompts"], list):
            for tp in data["thumbnail_prompts"]:
                if isinstance(tp, dict):
                    p_str = tp.get("prompt") or tp.get("thumbnail_prompt") or ""
                elif isinstance(tp, str):
                    p_str = tp
                else:
                    p_str = ""
                p_clean = p_str.strip()
                if p_clean and p_clean not in thumb_prompts:
                    thumb_prompts.append(p_clean)

        # 2. Check thumbnail_prompt.txt or thumbnail_prompts.txt (if JSON had no prompts or file exists)
        for tfilename in ["thumbnail_prompt.txt", "thumbnail_prompts.txt"]:
            tpath = folder / tfilename
            if tpath.exists():
                try:
                    text_content = tpath.read_text(encoding="utf-8")
                    sections = re.split(r'(?:^|\n)\s*(?:---|===)\s*Thumbnail Style\s*\d*[^-\n=]*\s*(?:---|===)', text_content, flags=re.IGNORECASE)
                    for sec in sections:
                        sec_s = sec.strip()
                        if not sec_s:
                            continue
                        m = re.search(r'Thumbnail Prompt(?:\s*\d+)?(?:\s*\([^)]*\))?:\s*([\s\S]+)', sec_s, flags=re.IGNORECASE)
                        if m:
                            body = m.group(1).strip()
                            body = re.sub(r'\n\s*(?:---|===).*', '', body, flags=re.DOTALL).strip()
                            if body and body not in thumb_prompts:
                                thumb_prompts.append(body)
                        else:
                            # Non-header text fallback
                            lines = [l.strip() for l in sec_s.split("\n") if l.strip() and not any(l.strip().lower().startswith(p) for p in ["title:", "topic:", "art style anchor:"])]
                            if lines:
                                body = " ".join(lines).strip()
                                if body and body not in thumb_prompts:
                                    thumb_prompts.append(body)

                    if not thumb_prompts:
                        for line in text_content.split("\n"):
                            m = re.search(r'Thumbnail Prompt(?:\s*\d+)?(?:\s*\([^)]*\))?:\s*(.+)', line.strip(), flags=re.IGNORECASE)
                            if m:
                                p_val = m.group(1).strip()
                                if p_val and p_val not in thumb_prompts:
                                    thumb_prompts.append(p_val)
                except Exception:
                    pass

        # 3. Check single thumbnail_prompt field in project.json
        if not thumb_prompts and data.get("thumbnail_prompt"):
            tp_str = str(data["thumbnail_prompt"]).strip()
            if tp_str:
                thumb_prompts.append(tp_str)

        return thumb_prompts

    def scan_projects(self, dir_path) -> list[Job]:
        master_folder = Path(dir_path)
        if not master_folder.exists():
            return []

        # Find all project folders: master_folder itself plus all child folders
        candidates = set()
        for marker in ["project.json", "metadata.json", "prompts.txt", "thumbnail_prompt.txt", "thumbnail_prompts.txt"]:
            if (master_folder / marker).exists():
                candidates.add(master_folder)
            for f in master_folder.rglob(marker):
                candidates.add(f.parent)

        jobs = []
        for folder in sorted(candidates, key=lambda p: str(p)):
            data = {}
            for json_name in ["project.json", "metadata.json"]:
                pjson = folder / json_name
                if pjson.exists():
                    try:
                        data = json.loads(pjson.read_text(encoding="utf-8"))
                        break
                    except Exception:
                        pass

            topic = data.get("title") or data.get("topic") or folder.name
            topic_slug = topic.replace(" ", "_").lower()

            # ── Scene Prompts ────────────────────────────────────────────────
            prompts_txt = folder / "prompts.txt"
            if prompts_txt.exists():
                try:
                    ptxt = prompts_txt.read_text(encoding="utf-8")
                    idx = 1
                    for line in ptxt.split("\n"):
                        if "Image Prompt:" in line:
                            prompt_str = line.split("Image Prompt:", 1)[1].strip()
                            if prompt_str:
                                jobs.append(Job(
                                    topic_name=topic,
                                    topic_slug=topic_slug,
                                    prompt_text=prompt_str,
                                    prompt_index=idx,
                                    project_folder=str(folder)
                                ))
                                idx += 1
                except Exception:
                    pass
            elif "prompts" in data and isinstance(data["prompts"], list):
                for idx, p_item in enumerate(data["prompts"], 1):
                    p_str = p_item.get("detailed_image_prompt") or p_item.get("prompt") if isinstance(p_item, dict) else str(p_item)
                    if p_str and p_str.strip():
                        jobs.append(Job(
                            topic_name=topic,
                            topic_slug=topic_slug,
                            prompt_text=p_str.strip(),
                            prompt_index=idx,
                            project_folder=str(folder)
                        ))
            elif "images" in data and isinstance(data["images"], list):
                for i, img in enumerate(data["images"], 1):
                    prompt = img.get("prompt", img.get("text", "")) if isinstance(img, dict) else str(img)
                    if prompt and prompt.strip():
                        jobs.append(Job(
                            topic_name=topic,
                            topic_slug=topic_slug,
                            prompt_text=prompt.strip(),
                            prompt_index=i,
                            project_folder=str(folder)
                        ))

            # ── Thumbnail Prompts ────────────────────────────────────────────
            thumb_prompts = self.extract_thumbnail_prompts(folder, data)
            for t_idx, tp_text in enumerate(thumb_prompts, 1):
                jobs.append(Job(
                    topic_name=topic,
                    topic_slug=topic_slug,
                    prompt_text=tp_text,
                    prompt_index=-(t_idx),
                    prompt_slug=f"thumbnail_{t_idx:02d}",
                    thumbnail_index=t_idx,
                    project_folder=str(folder),
                    aspect_ratio="16:9",
                    mode="image"
                ))

        return jobs

    def _on_scan_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Master Projects Directory")
        if not dir_path:
            return

        jobs = self.scan_projects(dir_path)

        if jobs:
            AppState.instance().queue_mgr.add_jobs(jobs)
            EventHub.instance().queue_changed.emit()
            QMessageBox.information(self, "Scan Complete", f"Added {len(jobs)} new jobs to the queue.")
        else:
            QMessageBox.information(self, "Scan Complete", "No valid project.json or prompts found.")

    def _on_clear(self):
        reply = QMessageBox.question(self, "Confirm Clear", "Are you sure you want to clear ALL jobs from the queue?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            AppState.instance().queue_mgr.clear()
            EventHub.instance().queue_changed.emit()

    def _on_retry(self):
        AppState.instance().queue_mgr.retry_failed()
        EventHub.instance().queue_changed.emit()
