import pytest
import json
import os
from pathlib import Path

from models import Job, JobStatus, Settings
from database import Database
from queue_manager import QueueManager
from app.core.app_state import AppState
from app.gui.tabs.queue_tab import QueueTab
from worker import compute_job_save_path

def test_thumbnail_scanning_and_queuing(tmp_path):
    # Initialize database and AppState
    db_file = str(tmp_path / "test.db")
    db = Database(db_file)
    qm = QueueManager(db)
    qm.load()

    app_state = AppState.instance()
    app_state.db = db
    app_state.queue_mgr = qm

    # Setup mock project directory
    proj = tmp_path / "my_project"
    proj.mkdir()

    pjson = proj / "project.json"
    pjson.write_text(json.dumps({
        "title": "Quantum Computing Breakthrough",
        "thumbnail_prompts": [
            {"style_id": "s1", "style_name": "Hero Prism", "prompt": "Prompt for thumbnail 1"},
            {"style_id": "s2", "style_name": "Matrix Glitch", "prompt": "Prompt for thumbnail 2"},
            {"style_id": "s3", "style_name": "Scale Clash", "prompt": "Prompt for thumbnail 3"}
        ]
    }), encoding="utf-8")

    prompts_txt = proj / "prompts.txt"
    prompts_txt.write_text("Image Prompt: Scene 1 detailed visual\nImage Prompt: Scene 2 detailed visual\n", encoding="utf-8")

    thumb_file = proj / "thumbnail_prompt.txt"
    thumb_file.write_text(
        "Title: Quantum Computing Breakthrough\nTopic: Quantum\n\n"
        "--- Thumbnail Style 1: Hero Prism ---\n"
        "Thumbnail Prompt: Prompt for thumbnail 1\n\n"
        "--- Thumbnail Style 2: Matrix Glitch ---\n"
        "Thumbnail Prompt: Prompt for thumbnail 2\n\n"
        "--- Thumbnail Style 3: Scale Clash ---\n"
        "Thumbnail Prompt: Prompt for thumbnail 3\n",
        encoding="utf-8"
    )

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    tab = QueueTab()
    # Call the REAL production method
    jobs = tab.scan_projects(tmp_path)

    assert len(jobs) == 5, f"Expected 2 scene jobs + 3 thumbnail jobs, got {len(jobs)}"
    scene_jobs = [j for j in jobs if j.thumbnail_index == 0]
    thumb_jobs = [j for j in jobs if j.thumbnail_index > 0]
    assert len(scene_jobs) == 2
    assert len(thumb_jobs) == 3
    assert [j.thumbnail_index for j in thumb_jobs] == [1, 2, 3]
    assert [j.prompt_slug for j in thumb_jobs] == ["thumbnail_01", "thumbnail_02", "thumbnail_03"]

def test_thumbnail_scanning_single_folder_direct(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    proj = tmp_path / "direct_project"
    proj.mkdir()

    (proj / "prompts.txt").write_text("Image Prompt: Scene A\n", encoding="utf-8")
    (proj / "thumbnail_prompt.txt").write_text(
        "--- Thumbnail Style 1: Retro ---\n"
        "Thumbnail Prompt: Detailed retro synthwave prompt\n"
        "Multi-line prompt text continuation\n\n"
        "--- Thumbnail Style 2: Modern ---\n"
        "Thumbnail Prompt: Clean minimal geometric composition\n",
        encoding="utf-8"
    )

    tab = QueueTab()
    # Scan passing the direct project directory path
    jobs = tab.scan_projects(proj)

    assert len(jobs) == 3, f"Expected 1 scene + 2 thumbnails, got {len(jobs)}"
    thumb_jobs = [j for j in jobs if j.thumbnail_index > 0]
    assert len(thumb_jobs) == 2
    assert "Multi-line prompt text continuation" in thumb_jobs[0].prompt_text

def test_thumbnail_scanning_corrupted_json_recovery(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    proj = tmp_path / "corrupted_project"
    proj.mkdir()

    # Corrupted project.json
    (proj / "project.json").write_text("{invalid json ...", encoding="utf-8")
    (proj / "prompts.txt").write_text("Image Prompt: Scene X\n", encoding="utf-8")
    (proj / "thumbnail_prompt.txt").write_text("Thumbnail Prompt: High contrast thumbnail\n", encoding="utf-8")

    tab = QueueTab()
    jobs = tab.scan_projects(proj)

    assert len(jobs) == 2
    thumb_jobs = [j for j in jobs if j.thumbnail_index > 0]
    assert len(thumb_jobs) == 1
    assert thumb_jobs[0].prompt_text == "High contrast thumbnail"

def test_worker_thumbnail_save_path(tmp_path):
    proj = tmp_path / "proj_x"
    proj.mkdir()

    job = Job(
        topic_name="Quantum",
        topic_slug="quantum",
        prompt_text="A dramatic quantum core",
        prompt_slug="thumbnail_02",
        thumbnail_index=2,
        project_folder=str(proj)
    )

    # Call real compute_job_save_path from worker.py
    save_path = compute_job_save_path(job)

    assert save_path == proj / "thumbnails" / "thumbnail_02.png"
    assert (proj / "thumbnails").is_dir()

def test_worker_thumbnail_save_path_no_project_folder(tmp_path):
    settings = Settings(output_dir=str(tmp_path / "custom_output"))

    job = Job(
        topic_name="Void",
        topic_slug="void",
        prompt_text="Void thumbnail",
        prompt_slug="thumbnail_01",
        thumbnail_index=1,
        project_folder=""
    )

    save_path = compute_job_save_path(job, settings=settings)
    assert save_path == tmp_path / "custom_output" / "thumbnails" / "thumbnail_01.png"
    assert (tmp_path / "custom_output" / "thumbnails").is_dir()
