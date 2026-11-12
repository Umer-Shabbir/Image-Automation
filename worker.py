# worker.py  v6.0
"""
AccountWorker for Google Flow Studio Batch Pro.
Handles job execution with character consistency tagging, model/aspect-ratio parameter routing, and recovery.
"""

import asyncio
import threading
import time
import queue
from pathlib import Path
from typing import Optional, Dict, Any, List

from models import Account, Job, JobStatus, AccountStatus, Settings, Workspace, Character
from automator import (
    GoogleFlowAutomator,
    QuotaLimitError, PolicyError,
    FlaggedAccountError, RateLimitError,
    LoginExpiredError, SkippedError
)
from queue_manager import QueueManager
from utils import build_final_prompt, generate_filename


def compute_job_save_path(job: Job, settings: Optional[Any] = None, mode: Optional[str] = None) -> Path:
    """
    Computes the destination file path for a Job.
    Guarantees that thumbnail jobs are saved into a dedicated 'thumbnails' subfolder,
    and all generations route reliably to their exact designated project locations.
    """
    import re
    from utils import generate_filename

    target_mode = mode or getattr(job, 'mode', None) or (getattr(settings, "generation_mode", "image") if settings else "image")
    ext = ".mp4" if str(target_mode).lower() == "video" else ".png"

    # 1. If explicit file_path already exists on job and ends with an image/video extension, honor it directly
    if getattr(job, 'file_path', None):
        candidate_fp = Path(job.file_path)
        if candidate_fp.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp", ".mp4"]:
            candidate_fp.parent.mkdir(parents=True, exist_ok=True)
            return candidate_fp

    p_idx = getattr(job, 'prompt_index', 0)
    t_idx = getattr(job, 'thumbnail_index', 0)
    is_thumbnail = (
        t_idx > 0
        or p_idx < 0
        or (p_idx <= 0 and ("thumbnail" in str(getattr(job, 'prompt_slug', '')).lower() or getattr(job, 'topic_slug', '') == 'thumbnail'))
    )

    proj_folder = getattr(job, 'project_folder', '')
    if not proj_folder and (getattr(job, 'topic_slug', '') or getattr(job, 'topic_name', '')):
        # Check if topic_slug / topic_name folder exists under output directories
        out_base = Path(getattr(settings, "output_dir", "output") if settings else "output")
        slug_or_name = getattr(job, 'topic_slug', '') or getattr(job, 'topic_name', '')
        candidate_dirs = [
            out_base / slug_or_name,
            Path("H:/Automation/output") / slug_or_name
        ]
        for cdir in candidate_dirs:
            if cdir.exists():
                proj_folder = str(cdir)
                break

    if proj_folder:
        proj_dir = Path(proj_folder)
        if is_thumbnail:
            img_dir = proj_dir / "thumbnails"
            img_dir.mkdir(parents=True, exist_ok=True)
            t_idx = getattr(job, 'thumbnail_index', 0)
            if not t_idx:
                m = re.search(r'\d+', str(getattr(job, 'prompt_slug', '')))
                if m:
                    t_idx = int(m.group(0))
                elif getattr(job, 'prompt_index', 0) < 0:
                    t_idx = abs(getattr(job, 'prompt_index', -1))
                else:
                    t_idx = 1
            filename = f"thumbnail_{t_idx:02d}{ext}"
            return img_dir / filename
        else:
            sub = "videos" if str(target_mode).lower() == "video" else "images"
            media_dir = proj_dir / sub
            media_dir.mkdir(parents=True, exist_ok=True)
            p_idx = getattr(job, 'prompt_index', 1) or 1
            filename = f"{p_idx:02d}{ext}"
            return media_dir / filename
    else:
        out_base = Path(getattr(settings, "output_dir", "output") if settings else "output")
        if is_thumbnail:
            img_dir = out_base / "thumbnails"
            img_dir.mkdir(parents=True, exist_ok=True)
            t_idx = getattr(job, 'thumbnail_index', 0) or 1
            filename = f"thumbnail_{t_idx:02d}{ext}"
            return img_dir / filename
        else:
            max_slug = getattr(settings, "max_slug_chars", 60) if settings else 60
            fn_template = getattr(settings, "filename_template", "{topicSlug}/{topicSlug}_{promptIndex}_{promptSlug}.png") if settings else "{topicSlug}/{topicSlug}_{promptIndex}_{promptSlug}.png"
            filename = generate_filename(
                fn_template,
                job,
                max_slug=max_slug,
                mode=target_mode
            )
            return out_base / filename



class AccountWorker:

    def __init__(
        self,
        account: Account,
        queue_mgr: QueueManager,
        settings: Settings,
        evt_q: queue.Queue,
        characters: Optional[Dict[str, Character]] = None,
    ):
        self.account    = account
        self.queue      = queue_mgr
        self.settings   = settings
        self.evt_q      = evt_q
        self.characters = characters or {}

        self._stop_evt      = threading.Event()
        self._pause_evt     = threading.Event()
        self._skip_evt      = threading.Event()
        self._thread        = None
        self._auto: Optional[GoogleFlowAutomator] = None
        self._topic         = None
        self._profile       = str(Path("profiles") / account.id)
        self._loop          = None

        self._start_time:        float = 0.0
        self._last_success_time: float = 0.0
        self._recovery_count:    int   = 0
        self._force_new_chat:    bool  = False
        self._session_gen_count: int   = 0

    # â”€â”€ Control â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def start(self):
        self._stop_evt.clear()
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request_stop(self):
        self._stop_evt.set()
        if self._auto:
            self._auto.running = False
        if self._loop and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(self._cancel_all_tasks)
            except Exception:
                pass

    def _cancel_all_tasks(self):
        try:
            for task in asyncio.all_tasks(self._loop):
                task.cancel()
        except Exception:
            pass

    def request_pause(self):
        self._pause_evt.set()
        self._emit("status", AccountStatus.PAUSED)

    def request_resume(self):
        self._pause_evt.clear()
        self._emit("status", AccountStatus.RUNNING)

    def request_skip(self):
        self._skip_evt.set()
        if self._auto:
            self._auto.running = False

    def request_recovery(self):
        self._force_new_chat = True
        if self._auto:
            self._auto.running = True

    def reset_recovery_count(self):
        self._recovery_count = 0

    def get_last_success_time(self) -> float:
        return self._last_success_time

    def get_start_time(self) -> float:
        return self._start_time

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def join(self, timeout: float = 5.0):
        if self._thread:
            self._thread.join(timeout)

    # â”€â”€ Test helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_login(self):
        if self._loop and self._auto and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._auto.test_login(), self._loop)

    def test_screenshot(self, path: Path):
        if self._loop and self._auto and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._auto.test_screenshot(path), self._loop)

    # â”€â”€ Internal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _emit(self, *args):
        self.evt_q.put((args[0], self.account.id) + args[1:])

    def _log(self, msg: str, level: str = "info"):
        self._emit("log", msg, level)

    def _check_hard_limit(self) -> bool:
        """
        Enforces Global Hard Generation Limit:
        Once an active account reaches this exact number of image generations,
        forces the account to go to sleep immediately—even if it has not encountered any generation failures yet.
        """
        hard_limit = getattr(self.settings, "hard_generation_limit", 0) or 0
        if hard_limit > 0 and self.account.images_session >= hard_limit:
            flagged_wait = getattr(self.settings, "flagged_sleep_time", 1800.0) or 1800.0
            self._log(
                f"Global Hard Generation Limit reached ({self.account.images_session}/{hard_limit}). "
                f"Forcing profile [{self.account.name}] to sleep for {int(flagged_wait // 60)} minutes.",
                "warning"
            )
            self.account.status = AccountStatus.SLEEPING
            self.account.sleep_until = time.time() + flagged_wait
            self._emit("status", AccountStatus.SLEEPING, flagged_wait)
            self._stop_evt.set()
            return True
        return False

    def _s(self, attr: str, default=None):
        return getattr(self.settings, attr, default)

    # â”€â”€ Thread entry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except asyncio.CancelledError:
            self._log("Worker loop cancelled", "info")
        except Exception as e:
            self._log(f"Worker crash: {e}", "error")
            self._emit("status", AccountStatus.ERROR)
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            except Exception:
                pass
            self._loop.close()
            self._loop = None
            self._emit("finished")

    # â”€â”€ Workspace helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _current_ws(self) -> Workspace:
        if 0 <= self.account.current_workspace_idx < len(self.account.workspaces):
            return self.account.workspaces[self.account.current_workspace_idx]
        return self.account.workspaces[0]

    def _mark_ws_limited(self):
        ws = self._current_ws()
        ws.exhausted = True
        ws.image_limit_until = time.time() + 86400
        self._emit("ws_exhausted", ws.name)

    def compute_save_path(self, job: Job, mode: Optional[str] = None) -> Path:
        return compute_job_save_path(job, self.settings, mode)

    def _check_and_update_project_folder(self, folder_path: str):
        if not folder_path:
            return

        import json
        from pathlib import Path

        folder_jobs = [j for j in self.queue.all_jobs() if getattr(j, 'project_folder', '') == folder_path]
        if not folder_jobs:
            return

        all_finished = True
        for j in folder_jobs:
            if j.status not in ("done", "skipped"):
                all_finished = False
                break

        if all_finished:
            pjson_path = Path(folder_path) / "project.json"
            if not pjson_path.exists():
                pjson_path = Path(folder_path) / "metadata.json"
            if pjson_path.exists():
                try:
                    with open(pjson_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    is_video = any(getattr(j, 'mode', 'image') == 'video' for j in folder_jobs)
                    stage_name = "VIDEOS_READY" if is_video else "IMAGES_READY"
                    data["stage"] = stage_name
                    data["status"] = "COMPLETED"

                    # Record saved thumbnail paths if available
                    thumb_dir = Path(folder_path) / "thumbnails"
                    if thumb_dir.exists():
                        t_files = sorted([
                            str(p.relative_to(Path(folder_path))).replace("\\", "/")
                            for p in thumb_dir.iterdir()
                            if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".webp", ".mp4")
                        ])
                        if t_files:
                            data["thumbnails"] = t_files

                    with open(pjson_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    self._log(f"Project state advanced to {stage_name} for {Path(folder_path).name}", "info")
                except Exception as e:
                    self._log(f"Error updating project.json for {Path(folder_path).name}: {e}", "warning")

    def _requeue_job(self, job: Job, reason: str):
        job.status              = JobStatus.PENDING
        job.error               = reason
        job.retry_count         = 0
        job.assigned_account_id = ""
        self.queue.update_job(job)
        self._emit("job_requeued", job.id, reason)
        self._log(f"Re-queued #{job.global_index} ({reason})", "warning")

    # â”€â”€ Main loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _main(self):
        color = self.account.color or "#4285F4"
        platform = self._s("generation_platform", "flow")

        if platform == "bulk_app":
            from bulk_automator import BulkAppAutomator
            self._auto = BulkAppAutomator(
                profile_dir   = self._profile,
                settings      = self.settings,
                log_callback  = self._log,
                account_color = color,
                account_name  = self.account.name,
            )
        else:
            self._auto = GoogleFlowAutomator(
                profile_dir    = self._profile,
                settings       = self.settings,
                log_callback   = self._log,
                account_color  = color,
                account_name   = self.account.name,
            )
        try:
            await self._auto.start()

            # Google Login wait
            login_timeout = self._s("login_wait_timeout", 150.0)
            if not await self._auto.check_login():
                self._emit("login_req")
                self._emit("status", AccountStatus.LOGIN_REQUIRED)
                self._log(f"Google login required — waiting up to {int(login_timeout)}s", "warning")
                waited = 0.0
                poll   = 3.0
                while waited < login_timeout:
                    if self._stop_evt.is_set():
                        return
                    await asyncio.sleep(poll)
                    waited += poll
                    if hasattr(self._auto, "goto_flow"):
                        await self._auto.goto_flow()
                    elif hasattr(self._auto, "ensure_app_ready"):
                        await self._auto.ensure_app_ready(10.0)
                    if await self._auto.check_login():
                        self._log("Google login verified ✅", "success")
                        break
                else:
                    self._log("Google login timeout — releasing worker slot", "error")
                    return

            self._emit("status", AccountStatus.RUNNING)
            plat_name = "Bulk Media Generator" if platform == "bulk_app" else "Google Flow"
            self._log(f"Running on {plat_name} [{self.account.name}]", "info")

            # Check if account is already at or past hard limit before starting
            if self._check_hard_limit():
                return

            if platform == "bulk_app":
                batch_size = max(1, self._s("bulk_batch_size", 10))
                while not self._stop_evt.is_set():
                    while self._pause_evt.is_set() and not self._stop_evt.is_set():
                        await asyncio.sleep(self._s("input_poll_interval", 0.30))
                    if self._stop_evt.is_set():
                        break

                    jobs = self.queue.get_next_jobs(max_count=batch_size, same_project_only=True)
                    if not jobs:
                        self._emit("status", AccountStatus.IDLE)
                        break

                    try:
                        await self._process_bulk_jobs(jobs)
                    except asyncio.CancelledError:
                        for j in jobs:
                            self._requeue_job(j, "worker_cancelled")
                        raise
                    except Exception as e:
                        self._log(f"Unhandled bulk batch error: {e}", "error")
                        for j in jobs:
                            self._requeue_job(j, f"unhandled_bulk_error_{e}")

                    if self._check_hard_limit():
                        if self._auto:
                            try:
                                await self._auto.stop()
                            except Exception:
                                pass
                        break

                    if not self._stop_evt.is_set():
                        delay = self._s("delay_between_prompts", 3.0)
                        await asyncio.sleep(delay)

            else:
                # Standard Google Flow per-job loop
                while not self._stop_evt.is_set():
                    while self._pause_evt.is_set() and not self._stop_evt.is_set():
                        await asyncio.sleep(self._s("input_poll_interval", 0.30))
                    if self._stop_evt.is_set():
                        break

                    job = self.queue.get_next_job()
                    if not job:
                        self._emit("status", AccountStatus.IDLE)
                        break

                    try:
                        await self._process_job(job)
                    except asyncio.CancelledError:
                        self._requeue_job(job, "worker_cancelled")
                        raise
                    except Exception as e:
                        self._log(f"Unhandled job error: {e}", "error")
                        self._requeue_job(job, f"unhandled_error_{e}")

                    if self._check_hard_limit():
                        if self._auto:
                            try:
                                await self._auto.stop()
                            except Exception:
                                pass
                        break

                    if not self._stop_evt.is_set():
                        delay = self._s("delay_between_prompts", 3.0)
                        await asyncio.sleep(delay)

        except asyncio.CancelledError:
            self._emit("status", AccountStatus.IDLE)
        except Exception as e:
            self._log(f"Fatal worker exception: {e}", "error")
            self._emit("status", AccountStatus.ERROR)
        finally:
            if self._auto:
                try:
                    await self._auto.stop()
                except Exception:
                    pass

    # â”€â”€ Job processing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    # ── Bulk Job processing ───────────────────────────────────────────────────

    def _resolve_job_preset(self, job: Job) -> dict:
        preset_name = self._s("style_preset", "")
        preset_data = {
            "preset_name": preset_name,
            "visual_style": "",
            "aspect_ratio": "",
            "negative_prompt": "",
            "cinematic_style": "",
            "character_consistency": "",
            "environment_consistency": "",
            "model": "",
            "mode": "",
        }

        proj_folder = getattr(job, "project_folder", None)
        if not proj_folder and (getattr(job, "topic_slug", "") or getattr(job, "topic_name", "")):
            slug = getattr(job, "topic_slug", "") or getattr(job, "topic_name", "")
            for base in [Path("H:/Automation/output"), Path(self._s("output_dir", "output"))]:
                cand = base / slug
                if (cand / "project.json").exists() or (cand / "metadata.json").exists():
                    proj_folder = str(cand)
                    break

        if proj_folder:
            import json
            pjson_path = Path(proj_folder) / "project.json"
            if not pjson_path.exists():
                pjson_path = Path(proj_folder) / "metadata.json"

            if pjson_path.exists():
                try:
                    pdata = json.loads(pjson_path.read_text(encoding="utf-8"))
                    preset_name = pdata.get("preset_name") or pdata.get("preset") or preset_name
                    preset_data["preset_name"] = preset_name
                except Exception:
                    pass

        if preset_name:
            try:
                import json, re
                registry = None
                possible_paths = [
                    Path("H:/Automation/Presets/master_presets_registry.json"),
                    Path(__file__).resolve().parent.parent / "Presets" / "master_presets_registry.json",
                    Path(__file__).resolve().parent / "Presets" / "master_presets_registry.json",
                    Path("Presets/master_presets_registry.json")
                ]
                for p in possible_paths:
                    if p.exists():
                        registry = json.loads(p.read_text(encoding="utf-8"))
                        break

                if registry:
                    matched_entry = None
                    if preset_name in registry:
                        matched_entry = registry[preset_name]
                    else:
                        norm = re.sub(r'[\s_\-]+(style[\s_\-]*pack|style|preset)$', '', preset_name.strip().lower())
                        for k, v in registry.items():
                            k_norm = re.sub(r'[\s_\-]+(style[\s_\-]*pack|style|preset)$', '', k.strip().lower())
                            if k.lower() == preset_name.lower() or k_norm == norm or k.lower() == norm:
                                matched_entry = v
                                break

                    if matched_entry:
                        ia = matched_entry.get("image_automation", {})
                        preset_data["visual_style"] = ia.get("visual_style", "")
                        preset_data["aspect_ratio"] = ia.get("aspect_ratio", "")
                        preset_data["negative_prompt"] = ia.get("negative_prompt", "")
                        preset_data["cinematic_style"] = ia.get("cinematic_style", "")
                        preset_data["character_consistency"] = ia.get("character_consistency", "")
                        preset_data["environment_consistency"] = ia.get("environment_consistency", "")
                        preset_data["model"] = ia.get("model", "")
                        preset_data["mode"] = ia.get("generation_mode", "")
            except Exception as e:
                self._log(f"Failed to load preset {preset_name}: {e}", "warning")

        return preset_data

    def _build_job_prompt(self, job: Job, preset_info: Optional[dict] = None) -> tuple[str, dict]:
        if preset_info is None:
            preset_info = self._resolve_job_preset(job)

        char_name = job.character_name or self._s("active_character_name", "")
        final_prompt = build_final_prompt(
            base=job.prompt_text,
            character_name=char_name,
            prefix=self._s("prompt_prefix", ""),
            suffix=self._s("prompt_suffix", ""),
            style=preset_info["visual_style"] or self._s("style_preset", ""),
            aspect_ratio=preset_info["aspect_ratio"] or job.aspect_ratio or self._s("aspect_ratio", "16:9"),
            negative_prompt=preset_info["negative_prompt"],
            cinematic_style=preset_info["cinematic_style"],
            character_consistency=preset_info["character_consistency"],
            environment_consistency=preset_info["environment_consistency"],
        )
        return final_prompt, preset_info

    async def _process_bulk_jobs(self, jobs: List[Job]):
        if not jobs:
            return

        pending_jobs = []
        min_bytes = self._s("min_image_bytes", 30_000)
        dedup_enabled = self._s("dedup_check", True)

        for job in jobs:
            save_path = compute_job_save_path(job, self.settings, "image")
            if dedup_enabled and save_path.exists() and save_path.stat().st_size >= min_bytes:
                job.status = JobStatus.DONE
                job.file_path = str(save_path)
                job.completed_at = time.time()
                self.queue.update_job(job)
                self._log(f"⏭ #{job.global_index} skipped — file exists: {save_path.name}", "info")
                self._emit("job_done", job.id, str(save_path))
            else:
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
                job.assigned_account_id = self.account.id
                self.queue.update_job(job)
                self._emit("job_start", job.id, job.prompt_text)
                pending_jobs.append(job)

        if not pending_jobs:
            self._check_and_update_project_folder(getattr(jobs[0], 'project_folder', ''))
            return

        # Prepare synthesized batch jobs with full style guide, negative prompts, and consistency directives
        import copy
        from utils import slugify
        cloned_batch_jobs: List[Job] = []
        batch_aspect_ratio = ""
        batch_preset_style = ""

        for j in pending_jobs:
            final_p, pinfo = self._build_job_prompt(j)
            cloned = copy.copy(j)
            # Ensure prompt_slug is locked to original prompt so file naming is unchanged
            if not getattr(cloned, "prompt_slug", None):
                cloned.prompt_slug = slugify(j.prompt_text)
            cloned.prompt_text = final_p
            cloned_batch_jobs.append(cloned)

            if not batch_aspect_ratio and pinfo.get("aspect_ratio"):
                batch_aspect_ratio = pinfo["aspect_ratio"]
            if not batch_preset_style and pinfo.get("visual_style"):
                batch_preset_style = pinfo["visual_style"]

        target_ratio = batch_aspect_ratio or getattr(self.settings, "aspect_ratio", "16:9") or "16:9"
        char_desc = ""
        first_job = pending_jobs[0]
        char_name = first_job.character_name or self._s("active_character_name", "")
        if char_name and char_name in self.characters:
            char_desc = self.characters[char_name].description or char_name

        self._log(
            f"▶ Bulk batch ({len(pending_jobs)} jobs) starting on [{self.account.name}] "
            f"| Aspect: {target_ratio} | Style: {batch_preset_style[:40] + '...' if batch_preset_style else 'None'}",
            "info"
        )

        results = await self._auto.run_bulk_generation(
            cloned_batch_jobs,
            aspect_ratio=target_ratio,
            character_desc=char_desc,
            style_desc=batch_preset_style,
        )

        now = time.time()
        batch_saved = 0
        for job in pending_jobs:
            res = results.get(job.id, {})
            if res.get("success") and res.get("file_path"):
                job.status = JobStatus.DONE
                job.file_path = res["file_path"]
                job.completed_at = now
                self.queue.update_job(job)
                batch_saved += 1
                self._emit("job_done", job.id, res["file_path"])
            else:
                err_msg = res.get("error", "bulk_generation_failed")
                self._log(f"Re-queuing failed bulk job #{job.global_index} ({err_msg})", "warning")
                self._requeue_job(job, err_msg)

        if batch_saved > 0:
            self._session_gen_count += batch_saved
            self.account.images_session += batch_saved
            self.account.images_total += batch_saved
            self._current_ws().images_generated += batch_saved
            self._last_success_time = now
            self.account.last_image_time = now
            self._emit("img_count", self.account.images_session, self.account.images_total)

            # JSON metadata sidecar for all saved files
            if self._s("save_metadata_json", False):
                import json as _json, datetime as _dt
                for job in pending_jobs:
                    res = results.get(job.id, {})
                    if res.get("success") and res.get("file_path"):
                        p = res["file_path"]
                        sidecar = Path(p).with_suffix(".json")
                        try:
                            final_p, _ = self._build_job_prompt(job)
                            sidecar.write_text(_json.dumps({
                                "prompt": job.prompt_text,
                                "final_prompt": final_p,
                                "character": job.character_name or self._s("active_character_name", ""),
                                "model": "bulk_app",
                                "aspect_ratio": target_ratio,
                                "mode": getattr(job, "mode", "image"),
                                "topic": job.topic_name,
                                "timestamp": _dt.datetime.now().isoformat(),
                                "account": self.account.name,
                            }, indent=2), encoding="utf-8")
                        except Exception:
                            pass

        self._check_and_update_project_folder(getattr(first_job, 'project_folder', ''))

    async def _process_job(self, job: Job):
        self._skip_evt.clear()
        if self._auto:
            self._auto.running = True

        do_new_chat = False
        if self._force_new_chat:
            do_new_chat = True
            self._force_new_chat = False
            self._session_gen_count = 0

        refresh_threshold = self._s("project_refresh_threshold", 20)
        if refresh_threshold > 0 and self._session_gen_count >= refresh_threshold:
            self._log(f"Project refresh threshold reached ({self._session_gen_count}/{refresh_threshold} generations). Starting new project...", "info")
            do_new_chat = True
            self._session_gen_count = 0

        mode = self._s("new_chat_mode", "per_topic")
        if mode == "per_prompt":
            do_new_chat = True
        elif mode == "per_topic" and job.topic_name != self._topic:
            do_new_chat = True
            self._topic = job.topic_name
            self._session_gen_count = 0

        # 1. Resolve character for consistency
        char_name = job.character_name or self._s("active_character_name", "")
        character_obj = self.characters.get(char_name)

        # 2. Build final prompt with @Character tag and resolved preset style guide
        final_prompt, preset_info = self._build_job_prompt(job)
        preset_mode = preset_info.get("mode", "")
        preset_model = preset_info.get("model", "")
        preset_aspect_ratio = preset_info.get("aspect_ratio", "")

        target_mode = preset_mode or getattr(job, 'mode', None) or self._s("generation_mode", "image")
        save_path = self.compute_save_path(job, target_mode)
        filename = save_path.name

        # Dedup check
        min_bytes = self._s("min_image_bytes", 30_000)
        if self._s("dedup_check", True) and save_path.exists() and save_path.stat().st_size >= min_bytes:
            job.status       = JobStatus.DONE
            job.file_path    = str(save_path)
            job.completed_at = time.time()
            self.queue.update_job(job)
            self._log(f"⏭ #{job.global_index} skipped — file exists: {save_path.name}", "info")
            self._emit("job_done", job.id, str(save_path))
            self._check_and_update_project_folder(getattr(job, 'project_folder', ''))
            return

        job.status              = JobStatus.RUNNING
        job.started_at          = time.time()
        job.assigned_account_id = self.account.id
        self.queue.update_job(job)

        self._emit("job_start", job.id, job.prompt_text)
        self._log(f"▶ #{job.global_index} [{job.topic_name}] {char_name or 'generic'} → {Path(filename).name}", "info")

        max_retries     = self._s("max_retries", 3)
        retry_delay     = self._s("retry_delay", 5.0)
        rate_limit_wait = self._s("rate_limit_wait", 300.0)
        retry           = 0

        # Round-robin model selection among all available Flow models to prevent rate limits
        from models import FlowModel
        all_models = FlowModel.ALL
        # Rotate model index per global_index or hash of job id
        model_idx = (job.global_index + hash(self.account.id)) % len(all_models)
        round_robin_model = all_models[model_idx]

        target_model = preset_model or job.model_name or round_robin_model
        target_ratio = preset_aspect_ratio or job.aspect_ratio or self._s("aspect_ratio", "16:9")

        while retry <= max_retries:
            if self._stop_evt.is_set():
                self._requeue_job(job, "worker_stopped")
                return

            try:
                paths = await self._auto.run_prompt(
                    prompt_text  = final_prompt,
                    save_path    = save_path,
                    model_name   = target_model,
                    mode         = target_mode,
                    aspect_ratio = target_ratio,
                    image_count  = getattr(self.settings, 'image_count', 'x1'),
                    character    = character_obj,
                    do_new_session = do_new_chat,
                )

                primary_path = paths[0] if paths else str(save_path)
                job.status            = JobStatus.DONE
                job.file_path         = ", ".join(paths) if paths else str(save_path)
                job.completed_at      = time.time()
                self.queue.update_job(job)
                self._check_and_update_project_folder(getattr(job, 'project_folder', ''))

                num_saved = len(paths)
                self._session_gen_count     += 1
                self.account.images_session += num_saved
                self.account.images_total   += num_saved
                self._current_ws().images_generated += num_saved
                now = time.time()
                self._last_success_time      = now
                self.account.last_image_time = now
                self._recovery_count         = 0

                # JSON metadata sidecar for all saved files
                if self._s("save_metadata_json", False):
                    import json as _json, datetime as _dt
                    for p in paths:
                        sidecar = Path(p).with_suffix(".json")
                        try:
                            sidecar.write_text(_json.dumps({
                                "prompt": job.prompt_text,
                                "final_prompt": final_prompt,
                                "character": char_name,
                                "model": target_model,
                                "aspect_ratio": target_ratio,
                                "mode": job.mode,
                                "topic": job.topic_name,
                                "timestamp": _dt.datetime.now().isoformat(),
                                "account": self.account.name,
                            }, indent=2), encoding="utf-8")
                        except Exception:
                            pass

                self._emit("job_done", job.id, primary_path)
                self._emit("img_count", self.account.images_session, self.account.images_total)
                self._log(f"✅ #{job.global_index} → {Path(primary_path).name} ({num_saved} images)", "success")
                if self._check_hard_limit():
                    if self._auto:
                        try:
                            await self._auto.stop()
                        except Exception:
                            pass
                return

            except FlaggedAccountError as e:
                flagged_wait = self._s("flagged_sleep_time", 1800.0)
                self._log(f"Profile flagged for unusual activity! Closing browser and putting account to sleep for {int(flagged_wait//60)} minutes.", "warning")
                self.account.status = AccountStatus.SLEEPING
                self.account.sleep_until = time.time() + flagged_wait
                self._emit("status", AccountStatus.SLEEPING, flagged_wait)
                self._requeue_job(job, "account_flagged_sleeping")

                # Immediately close browser so profile window is dismissed
                if self._auto:
                    try:
                        await self._auto.stop()
                    except Exception:
                        pass

                # Return immediately so this worker terminates cleanly, frees its slot,
                # and allows the engine orchestrator to open another profile immediately.
                self._stop_evt.set()
                return

            except QuotaLimitError:
                ws = self._current_ws().name
                self._log(f"Google Flow quota reached on '{ws}'", "warning")
                self._emit("image_limit", ws)
                self._emit("status", AccountStatus.IMAGE_LIMITED)
                self._mark_ws_limited()
                self._requeue_job(job, "quota_limit_reached")
                if self._auto:
                    try:
                        await self._auto.stop()
                    except Exception:
                        pass
                self._stop_evt.set()
                return

            except RateLimitError:
                self._log("Google Flow rate limited. Re-queuing job and yielding slot.", "warning")
                self._emit("status", AccountStatus.RATE_LIMITED)
                self._requeue_job(job, "rate_limit_exceeded")
                if self._auto:
                    try:
                        await self._auto.stop()
                    except Exception:
                        pass
                self._stop_evt.set()
                return

            except PolicyError as e:
                self._log(f"Google Safety Policy: {e}", "warning")
                job.status       = JobStatus.SKIPPED
                job.error        = f"policy: {e}"
                job.completed_at = time.time()
                self.queue.update_job(job)
                self._check_and_update_project_folder(getattr(job, 'project_folder', ''))
                self._emit("job_skip", job.id, "policy_violation")
                return

            except LoginExpiredError:
                self._log("Google session expired", "warning")
                self._emit("login_expired")
                self._emit("status", AccountStatus.LOGIN_EXPIRED)
                self._requeue_job(job, "session_expired")
                self._stop_evt.set()
                return

            except SkippedError:
                job.status       = JobStatus.SKIPPED
                job.error        = "user_skipped"
                job.completed_at = time.time()
                self.queue.update_job(job)
                self._check_and_update_project_folder(getattr(job, 'project_folder', ''))
                self._emit("job_skip", job.id, "user_skipped")
                return

            except Exception as e:
                self._log(f"Generation issue: {e} (attempt {retry+1}/{max_retries+1})", "warning")
                retry += 1
                if retry >= 2:
                    do_new_chat = True
                    self._session_gen_count = 0
                if retry <= max_retries:
                    await asyncio.sleep(retry_delay)
                    continue

        self._log(f"âŒ #{job.global_index} â€” {max_retries+1} attempts exhausted, marking failed", "error")
        job.status       = JobStatus.FAILED
        job.error        = f"failed_{max_retries+1}_attempts"
        job.completed_at = time.time()
        self.queue.update_job(job)
        self._emit("job_fail", job.id, f"Failed after {max_retries+1} attempts")
