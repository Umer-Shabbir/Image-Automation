import os
import time
import queue
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

from models import Account, AccountStatus, Job, JobStatus, Settings, GenerationPlatform
from queue_manager import QueueManager
from database import Database
from app.core.engine import EngineThread
from worker import AccountWorker


class TestNewFeatures:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = str(tmp_path / "test_features.db")
        self.db = Database(self.db_path)
        self.queue_mgr = QueueManager(self.db)
        self.queue_mgr.load()

    def test_settings_platform_and_hard_limit_persistence(self):
        s = Settings()
        s.generation_platform = GenerationPlatform.BULK_APP
        s.bulk_app_url = "https://gemini.google.com/share/79e5de5150e6"
        s.bulk_batch_size = 250
        s.hard_generation_limit = 100

        self.db.save_settings(s)
        loaded = self.db.get_settings()

        assert loaded.generation_platform == GenerationPlatform.BULK_APP
        assert loaded.bulk_app_url == "https://gemini.google.com/share/79e5de5150e6"
        assert loaded.bulk_batch_size == 250
        assert loaded.hard_generation_limit == 100

    def test_settings_tab_bulk_batch_size_range(self):
        from app.gui.tabs.settings_tab import SettingsTab
        from app.core.app_state import AppState
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        AppState.instance().db = self.db
        tab = SettingsTab()
        assert tab.val_bulk_batch_size.maximum() >= 1000
        tab.val_bulk_batch_size.setValue(150)
        assert tab.val_bulk_batch_size.value() == 150

    def test_queue_manager_get_next_jobs_atomic_grouping(self):
        jobs = [
            Job(id="j1", global_index=0, project_folder="proj_A", prompt_text="Prompt 1"),
            Job(id="j2", global_index=1, project_folder="proj_A", prompt_text="Prompt 2"),
            Job(id="j3", global_index=2, project_folder="proj_B", prompt_text="Prompt 3"),
            Job(id="j4", global_index=3, project_folder="proj_A", prompt_text="Prompt 4"),
        ]
        self.queue_mgr.add_jobs(jobs)

        # Batch retrieval with same_project_only=True should only pull proj_A jobs
        batch = self.queue_mgr.get_next_jobs(max_count=2, same_project_only=True)
        assert len(batch) == 2
        assert batch[0].id == "j1"
        assert batch[1].id == "j2"
        assert all(j.status == JobStatus.RUNNING for j in batch)

        # Next batch for proj_A
        batch2 = self.queue_mgr.get_next_jobs(max_count=2, same_project_only=True)
        # Note: j3 is proj_B so cursor will skip it if same_project_only matches first pending (proj_B)
        assert len(batch2) >= 1
        assert batch2[0].id == "j3"
        assert batch2[0].project_folder == "proj_B"

    def test_strict_global_round_robin_rotation(self):
        """
        Verify the exact requirement:
        If Account 1 runs and goes to sleep, Account 2 starts.
        Even if Account 1's sleep timer finishes while Account 2 is running,
        when Account 2 goes to sleep, Account 3 must open next (not Account 1).
        """
        acct1 = Account(id="acct_1", name="Account 1", enabled=True, status="idle")
        acct2 = Account(id="acct_2", name="Account 2", enabled=True, status="idle")
        acct3 = Account(id="acct_3", name="Account 3", enabled=True, status="idle")
        self.db.save_account(acct1)
        self.db.save_account(acct2)
        self.db.save_account(acct3)

        # Add jobs
        jobs = [Job(id=f"job_{i}", prompt_text=f"Prompt {i}") for i in range(10)]
        self.queue_mgr.add_jobs(jobs)

        # Setup EngineThread
        settings = Settings(max_parallel_accounts=1)
        self.db.save_settings(settings)
        engine = EngineThread(self.db, self.queue_mgr)
        engine.is_running = True
        engine.is_paused = False

        with patch("app.core.engine.AccountWorker") as MockWorker:
            # Step 1: Initial orchestration -> Account 1 starts
            engine._orchestrate_workers()
            assert "acct_1" in engine.workers
            assert engine._last_selected_account_id == "acct_1"

            # Step 2: Account 1 goes to sleep
            acct1 = [a for a in self.db.get_accounts() if a.id == "acct_1"][0]
            acct1.status = "sleeping"
            acct1.sleep_until = time.time() + 1800
            self.db.save_account(acct1)
            # Worker finishes
            del engine.workers["acct_1"]

            # Step 3: Orchestrate -> Account 2 must start
            engine._orchestrate_workers()
            assert "acct_2" in engine.workers
            assert engine._last_selected_account_id == "acct_2"

            # Step 4: WHILE Account 2 is running, Account 1 wakes up!
            acct1 = [a for a in self.db.get_accounts() if a.id == "acct_1"][0]
            acct1.status = "idle"
            acct1.sleep_until = 0.0
            self.db.save_account(acct1)

            # Step 5: Account 2 goes to sleep
            acct2 = [a for a in self.db.get_accounts() if a.id == "acct_2"][0]
            acct2.status = "sleeping"
            acct2.sleep_until = time.time() + 1800
            self.db.save_account(acct2)
            del engine.workers["acct_2"]

            # Step 6: Orchestrate -> Account 3 MUST START NEXT (NOT Account 1)!
            engine._orchestrate_workers()
            assert "acct_3" in engine.workers, f"Expected acct_3 to start, but workers were: {list(engine.workers.keys())}"
            assert "acct_1" not in engine.workers
            assert engine._last_selected_account_id == "acct_3"

            # Step 7: Account 3 goes to sleep -> Now and only now does rotation wrap to Account 1
            acct3 = [a for a in self.db.get_accounts() if a.id == "acct_3"][0]
            acct3.status = "sleeping"
            acct3.sleep_until = time.time() + 1800
            self.db.save_account(acct3)
            del engine.workers["acct_3"]

            engine._orchestrate_workers()
            assert "acct_1" in engine.workers
            assert engine._last_selected_account_id == "acct_1"

    def test_hard_generation_limit_forces_sleep(self, tmp_path):
        """
        Verify that when an account reaches the exact hard generation limit,
        it is immediately forced to sleep with status='sleeping' and sleep_until set.
        """
        account = Account(id="test_acct", name="Test Account", enabled=True, status="idle")
        self.db.save_account(account)

        settings = Settings(hard_generation_limit=5, flagged_sleep_time=1800.0)
        import queue
        evt_q = queue.Queue()

        worker = AccountWorker(
            account=account,
            queue_mgr=self.queue_mgr,
            settings=settings,
            evt_q=evt_q
        )

        # Under limit: 4 generations
        worker.account.images_session = 4
        assert worker._check_hard_limit() is False
        assert worker.account.status != AccountStatus.SLEEPING

        # Reached exact limit: 5 generations
        worker.account.images_session = 5
        assert worker._check_hard_limit() is True
        assert worker.account.status == AccountStatus.SLEEPING
        assert worker.account.sleep_until > time.time() + 1700
        assert worker._stop_evt.is_set()

        # Check emitted event
        events = []
        while not evt_q.empty():
            events.append(evt_q.get_nowait())
        
        status_evts = [e for e in events if e[0] == "status"]
        assert len(status_evts) > 0
        assert status_evts[0][2] == AccountStatus.SLEEPING
        assert status_evts[0][3] == 1800.0

    @pytest.mark.anyio
    async def test_bulk_automator_1_to_1_tracking_and_saving(self, tmp_path):
        """
        Verify BulkAppAutomator extracts generatedImages and maps each prompt index
        accurately to the job destination path without cross-contamination.
        """
        from bulk_automator import BulkAppAutomator

        settings = Settings(min_image_bytes=10)
        automator = BulkAppAutomator(
            profile_dir=str(tmp_path / "profile"),
            settings=settings,
            account_name="Bulk Test Account"
        )

        automator.ensure_app_ready = AsyncMock(return_value=True)
        
        # Create 3 jobs for Project X
        proj_dir = tmp_path / "Project_X"
        jobs = [
            Job(id="job_0", global_index=0, project_folder=str(proj_dir), prompt_text="Prompt Zero", prompt_index=1),
            Job(id="job_1", global_index=1, project_folder=str(proj_dir), prompt_text="Prompt One", prompt_index=2),
            Job(id="job_2", global_index=2, project_folder=str(proj_dir), prompt_text="Prompt Two", prompt_index=3),
        ]

        # Fake Base64 1x1 png images
        import base64
        fake_bytes = b"FakeImageDataForTestingExactOutputBytes1234567890"
        fake_b64 = base64.b64encode(fake_bytes).decode("ascii")

        mock_frame = AsyncMock()
        mock_frame.select_option = AsyncMock()
        mock_frame.fill = AsyncMock()
        mock_frame.evaluate = AsyncMock(side_effect=[
            None, # dispatchEvent
            # Polling status return
            {"isGen": False, "progText": "Generation Complete!", "progWidth": "100%", "completedCards": 3, "failedCards": 0},
            # image_data_map return
            {
                "0": {"url": f"data:image/png;base64,{fake_b64}", "prompt": "Prompt Zero", "status": "success"},
                "1": {"url": f"data:image/png;base64,{fake_b64}", "prompt": "Prompt One", "status": "success"},
                "2": {"url": f"data:image/png;base64,{fake_b64}", "prompt": "Prompt Two", "status": "success"},
            }
        ])
        mock_btn = AsyncMock()
        mock_btn.click = AsyncMock()
        mock_frame.query_selector = AsyncMock(return_value=mock_btn)

        automator._get_app_frame = AsyncMock(return_value=mock_frame)

        results = await automator.run_bulk_generation(jobs)

        assert len(results) == 3
        for idx, job in enumerate(jobs):
            res = results[job.id]
            assert res["success"] is True
            saved_file = Path(res["file_path"])
            assert saved_file.exists()
            assert saved_file.read_bytes() == fake_bytes
            # Verify correct project isolation
            assert str(proj_dir) in str(saved_file)
            assert f"{idx+1:02d}.png" == saved_file.name

        # Verify that prompts are filled separated by an empty line (\n\n)
        fill_calls = mock_frame.fill.call_args_list
        prompt_fills = [args[1] for args, _ in fill_calls if args[0] == '#prompt-input' and args[1] != '']
        assert len(prompt_fills) > 0
        expected_bulk_text = "Prompt Zero\n\nPrompt One\n\nPrompt Two"
        assert prompt_fills[0] == expected_bulk_text

    def test_parallel_concurrency_respected_in_bulk_app_mode(self):
        """
        Verify that when max_parallel_accounts is set to 5 in Bulk App mode,
        the EngineThread launches all 5 accounts concurrently as requested.
        """
        for i in range(1, 6):
            self.db.save_account(Account(id=f"acct_{i}", name=f"Account {i}", enabled=True, status="idle"))

        # Add jobs
        jobs = [Job(id=f"job_{i}", prompt_text=f"Prompt {i}") for i in range(20)]
        self.queue_mgr.add_jobs(jobs)

        settings = Settings(
            max_parallel_accounts=5,
            generation_platform=GenerationPlatform.BULK_APP,
            account_start_delay=0.0  # instant for test
        )
        self.db.save_settings(settings)

        engine = EngineThread(self.db, self.queue_mgr)
        engine.is_running = True
        engine.is_paused = False

        with patch("app.core.engine.AccountWorker") as MockWorker:
            engine._orchestrate_workers()
            # Must launch all 5 accounts concurrently
            assert len(engine.workers) == 5
            for i in range(1, 6):
                assert f"acct_{i}" in engine.workers

    @pytest.mark.anyio
    async def test_bulk_jobs_resolve_preset_and_synthesize_style_guide(self, tmp_path):
        """
        Verify that AccountWorker._process_bulk_jobs extracts the preset from project.json,
        loads master_presets_registry.json, and synthesizes the style guide, cinematic style,
        and negative prompt into the prompts passed to run_bulk_generation().
        """
        import json
        import queue
        from models import JobStatus

        # 1. Setup a project folder with a preset
        proj_dir = tmp_path / "Project_Blueprint"
        proj_dir.mkdir(parents=True, exist_ok=True)
        pjson = proj_dir / "project.json"
        pjson.write_text(json.dumps({"preset_name": "blueprint"}), encoding="utf-8")

        # 2. Setup job with raw prompt
        raw_prompt = "Burj Khalifa: Engineering the World's Tallest Skyscraper"
        job = Job(
            id="job_bp_01",
            global_index=1,
            project_folder=str(proj_dir),
            prompt_text=raw_prompt,
            status=JobStatus.PENDING,
            prompt_slug="burj-khalifa-skyscraper"
        )
        self.queue_mgr.add_jobs([job])

        account = Account(id="acct_bp", name="BP Test Account", enabled=True, status="idle")
        settings = Settings(
            generation_platform=GenerationPlatform.BULK_APP,
            aspect_ratio="16:9",
            dedup_check=False
        )

        worker = AccountWorker(
            account=account,
            queue_mgr=self.queue_mgr,
            settings=settings,
            evt_q=queue.Queue()
        )

        # Mock automator
        mock_auto = AsyncMock()
        fake_saved_img = str(proj_dir / "images" / "01.png")
        Path(fake_saved_img).parent.mkdir(parents=True, exist_ok=True)
        Path(fake_saved_img).write_bytes(b"PNG_DATA_1234567890")

        mock_auto.run_bulk_generation = AsyncMock(return_value={
            job.id: {
                "success": True,
                "file_path": fake_saved_img,
                "error": ""
            }
        })
        worker._auto = mock_auto

        # 3. Process bulk jobs
        await worker._process_bulk_jobs([job])

        # Verify run_bulk_generation was called
        assert mock_auto.run_bulk_generation.called
        submitted_jobs, kwargs = mock_auto.run_bulk_generation.call_args[0], mock_auto.run_bulk_generation.call_args[1]
        assert len(submitted_jobs[0]) == 1
        submitted_job = submitted_jobs[0][0]

        # 4. Verify prompt synthesis in the submitted job
        # It must contain the raw prompt AND the preset's visual style, cinematic style, and negative prompt
        assert raw_prompt in submitted_job.prompt_text
        assert "style: engineering blueprint style" in submitted_job.prompt_text
        assert "avoiding: no color fills beyond the two-tone scheme" in submitted_job.prompt_text
        assert "engineering blueprint style" in kwargs.get("style_desc", "")

        # 5. Verify the original job in memory and queue retained its clean canonical prompt
        assert job.prompt_text == raw_prompt
        assert job.status == JobStatus.DONE
        assert job.file_path == fake_saved_img

    def test_preset_lookup_case_and_suffix_normalization(self, tmp_path):
        from worker import AccountWorker
        import json

        proj_dir = tmp_path / "test_norm_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        # Test with capitalized and suffixed name
        (proj_dir / "project.json").write_text(json.dumps({"preset_name": "Blueprint_Style_Pack"}), encoding="utf-8")

        job = Job(id="norm_job", project_folder=str(proj_dir), prompt_text="Test prompt")
        account = Account(id="acct_norm", name="Norm Account", enabled=True)
        worker = AccountWorker(account=account, queue_mgr=self.queue_mgr, settings=Settings(), evt_q=queue.Queue())

        preset_info = worker._resolve_job_preset(job)
        assert preset_info["visual_style"] != "", "Should resolve visual style despite case/suffix variation"
        assert "blueprint" in preset_info["visual_style"].lower()
        assert preset_info["aspect_ratio"] == "16:9"
        assert preset_info["negative_prompt"] != ""

    def test_compute_job_save_path_routing_and_explicit_path(self, tmp_path):
        from worker import compute_job_save_path

        # 1. Explicit file path with extension should be strictly honored
        explicit_path = tmp_path / "custom_dir" / "my_custom_image.png"
        job1 = Job(id="j_exp", file_path=str(explicit_path), prompt_text="Prompt 1")
        p1 = compute_job_save_path(job1, None, "image")
        assert p1 == explicit_path

        # 2. Project folder with normal image
        proj_dir = tmp_path / "my_project"
        job2 = Job(id="j_proj", project_folder=str(proj_dir), prompt_index=5, prompt_text="Prompt 2")
        p2 = compute_job_save_path(job2, None, "image")
        assert p2 == proj_dir / "images" / "05.png"

        # 3. Project folder with thumbnail
        job3 = Job(id="j_thumb", project_folder=str(proj_dir), thumbnail_index=2, prompt_text="Thumb")
        p3 = compute_job_save_path(job3, None, "image")
        assert p3 == proj_dir / "thumbnails" / "thumbnail_02.png"

        # 4. Empty project_folder but topic_slug matches an existing folder in output_dir
        out_dir = tmp_path / "global_output"
        cand_proj = out_dir / "great_pyramids"
        cand_proj.mkdir(parents=True, exist_ok=True)
        settings = Settings(output_dir=str(out_dir))
        job4 = Job(id="j_slug", topic_slug="great_pyramids", prompt_index=3, prompt_text="Pyramids")
        p4 = compute_job_save_path(job4, settings, "image")
        assert p4 == cand_proj / "images" / "03.png"
