import os
import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from models import Account, Job, JobStatus, AccountStatus, Settings
from queue_manager import QueueManager
from database import Database
from automator import _sanitize_profile_preferences
from app.core.engine import EngineThread

def test_sanitize_profile_preferences(tmp_path):
    pref_file = tmp_path / "Default" / "Preferences"
    pref_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Simulate a corrupted preference with 125% zoom and off-screen window placement
    broken_prefs = {
        "partition": {
            "per_host_zoom_levels": {
                "x": {
                    "flow.google.com": {"zoom_level": 1.2239}
                }
            }
        },
        "default_zoom_level": 1.5,
        "browser": {
            "window_placement": {
                "maximized": False,
                "top": 10,
                "left": 10,
                "bottom": 930,
                "right": 1470,
                "work_area_bottom": 870,
                "work_area_right": 1440
            }
        }
    }
    pref_file.write_text(json.dumps(broken_prefs), encoding="utf-8")
    
    _sanitize_profile_preferences(tmp_path)
    
    cleaned = json.loads(pref_file.read_text(encoding="utf-8"))
    assert cleaned["partition"]["per_host_zoom_levels"] == {"x": {}}
    assert "default_zoom_level" not in cleaned
    assert cleaned["browser"]["window_placement"]["maximized"] is True
    assert cleaned["browser"]["window_placement"]["top"] == 0
    assert cleaned["browser"]["window_placement"]["left"] == 0

def test_account_sleep_until_persistence(tmp_path):
    db_file = str(tmp_path / "test_sleep.db")
    db = Database(db_file)
    
    now = time.time()
    acct = Account(
        id="acc_1",
        name="Account 1",
        status=AccountStatus.SLEEPING,
        sleep_until=now + 1800.0
    )
    db.save_account(acct)
    
    loaded = {a.id: a for a in db.get_accounts()}
    assert "acc_1" in loaded
    assert loaded["acc_1"].status == AccountStatus.SLEEPING
    assert loaded["acc_1"].sleep_until == pytest.approx(now + 1800.0, rel=1e-3)

def test_engine_replaces_sleeping_profile_to_meet_concurrency(tmp_path):
    db_file = str(tmp_path / "test_engine.db")
    db = Database(db_file)
    qm = QueueManager(db)
    qm.load()
    
    # 3 enabled accounts, max_parallel = 2
    settings = db.get_settings()
    settings.max_parallel_accounts = 2
    db.save_settings(settings)
    
    acct1 = Account(id="acc_1", name="Profile 1", enabled=True, status=AccountStatus.IDLE)
    acct2 = Account(id="acc_2", name="Profile 2", enabled=True, status=AccountStatus.IDLE)
    acct3 = Account(id="acc_3", name="Profile 3", enabled=True, status=AccountStatus.IDLE)
    db.save_account(acct1)
    db.save_account(acct2)
    db.save_account(acct3)
    
    # Add pending jobs to queue
    qm.add_jobs([
        Job(prompt_text="Job 1"),
        Job(prompt_text="Job 2"),
        Job(prompt_text="Job 3"),
    ])
    
    engine = EngineThread(db, qm)
    
    # Mock AccountWorker to avoid actual browser launch
    with patch("app.core.engine.AccountWorker") as MockWorker:
        running_workers = {}
        def fake_worker_init(account, queue_mgr, settings, evt_q, characters):
            mock_w = MagicMock()
            mock_w.account = account
            mock_w.is_running.return_value = True
            running_workers[account.id] = mock_w
            return mock_w
        MockWorker.side_effect = fake_worker_init
        
        # Start batch with parallel_count = 2
        engine.start_batch(parallel_count=2)
        
        # Initial state: 2 workers started (Profile 1, Profile 2)
        assert len(engine.workers) == 2
        assert "acc_1" in engine.workers
        assert "acc_2" in engine.workers
        assert "acc_3" not in engine.workers
        
        # Simulate Profile 1 getting flagged and put to sleep
        # The worker terminates and notifies engine
        running_workers["acc_1"].is_running.return_value = False
        engine._dispatch_event(("status", "acc_1", AccountStatus.SLEEPING, 1800.0))
        engine._dispatch_event(("finished", "acc_1"))
        
        # Now engine should have cleaned up acc_1 and started acc_3 to maintain 2 concurrent workers!
        assert len(engine.workers) == 2
        assert "acc_1" not in engine.workers
        assert "acc_2" in engine.workers
        assert "acc_3" in engine.workers
        
        # Profile 1 is sleeping in database
        acc1_db = {a.id: a for a in db.get_accounts()}["acc_1"]
        assert acc1_db.status == AccountStatus.SLEEPING
        assert acc1_db.sleep_until > time.time()
        
        # Clean shutdown
        engine.stop_batch()

def test_database_and_engine_recovers_stranded_running_accounts(tmp_path):
    db_file = str(tmp_path / "test_engine.db")
    db = Database(db_file)
    qm = QueueManager(db)
    qm.load()

    # Create account and job left in 'running' status
    acct = Account(id="acc_stranded", name="Stranded Profile", enabled=True, status="running")
    db.save_account(acct)
    job = Job(id="job_stranded", prompt_text="Stranded Job", status=JobStatus.RUNNING, assigned_account_id="acc_stranded")
    db.save_job(job)

    # 1. Test database.recover_interrupted_jobs() resets account to idle
    recovered_count = db.recover_interrupted_jobs()
    assert recovered_count == 1
    reloaded_acct = {a.id: a for a in db.get_accounts()}["acc_stranded"]
    assert reloaded_acct.status == "idle"
    reloaded_job = [j for j in db.get_jobs() if j.id == "job_stranded"][0]
    assert reloaded_job.status == JobStatus.PENDING

    # 2. Test engine._orchestrate_workers() resets orphaned running account
    reloaded_acct.status = "running"
    db.save_account(reloaded_acct)
    engine = EngineThread(db, qm)
    engine.is_running = True
    engine._orchestrate_workers()
    assert {a.id: a for a in db.get_accounts()}["acc_stranded"].status == "idle"


def test_reset_account_sleep_database(tmp_path):
    db_file = str(tmp_path / "test_reset_db.db")
    db = Database(db_file)

    now = time.time()
    acct1 = Account(
        id="acc_sleep1",
        name="Sleeping Profile 1",
        status=AccountStatus.SLEEPING,
        sleep_until=now + 1800.0,
        images_session=50,
        error_message="flagged"
    )
    acct2 = Account(
        id="acc_sleep2",
        name="Sleeping Profile 2",
        status=AccountStatus.SLEEPING,
        sleep_until=now + 3600.0,
        images_session=25,
        error_message="quota"
    )
    db.save_account(acct1)
    db.save_account(acct2)

    # 1. Reset single account sleep
    db.reset_account_sleep("acc_sleep1")
    reloaded = {a.id: a for a in db.get_accounts()}
    assert reloaded["acc_sleep1"].status == "idle"
    assert reloaded["acc_sleep1"].sleep_until == 0.0
    assert reloaded["acc_sleep1"].images_session == 0
    assert reloaded["acc_sleep1"].error_message == ""
    # Account 2 remains sleeping
    assert reloaded["acc_sleep2"].status == AccountStatus.SLEEPING

    # 2. Reset all sleeping accounts
    count = db.reset_all_sleeping_accounts()
    assert count == 1
    reloaded2 = {a.id: a for a in db.get_accounts()}
    assert reloaded2["acc_sleep2"].status == "idle"
    assert reloaded2["acc_sleep2"].sleep_until == 0.0
    assert reloaded2["acc_sleep2"].images_session == 0


def test_reset_account_sleep_engine(tmp_path):
    db_file = str(tmp_path / "test_reset_engine.db")
    db = Database(db_file)
    qm = QueueManager(db)
    qm.load()

    now = time.time()
    acct = Account(
        id="acc_sleeping_eng",
        name="Sleeping Eng",
        status=AccountStatus.SLEEPING,
        sleep_until=now + 1800.0,
        images_session=10
    )
    db.save_account(acct)

    engine = EngineThread(db, qm)
    engine.reset_account_sleep("acc_sleeping_eng")

    reloaded = {a.id: a for a in db.get_accounts()}["acc_sleeping_eng"]
    assert reloaded.status == "idle"
    assert reloaded.sleep_until == 0.0
    assert reloaded.images_session == 0


