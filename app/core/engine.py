import asyncio
import queue
import threading
import time
from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal, QThread, Slot

from app.core.app_state import AppState
from app.core.events import EventHub
from worker import AccountWorker

class EngineThread(QThread):
    def __init__(self, db, queue_mgr, parent=None):
        super().__init__(parent)
        self.db = db
        self.queue_mgr = queue_mgr
        self.workers: Dict[str, AccountWorker] = {}
        self._workers_lock = threading.RLock()
        self.evt_q = queue.Queue()
        self.is_running = False
        self.is_paused = False
        self._loop = None
        self._stop_poll_evt = threading.Event()
        self._last_selected_account_id: Optional[str] = None

    def run(self):
        # Setup an asyncio loop inside this QThread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._stop_poll_evt.clear()
        last_orchestrate_time = 0.0

        # Continuously poll the evt_q for updates from workers and maintain concurrency
        while not self._stop_poll_evt.is_set():
            try:
                # 1. Process worker events
                try:
                    evt = self.evt_q.get(timeout=0.2)
                    self._dispatch_event(evt)
                    while not self.evt_q.empty():
                        self._dispatch_event(self.evt_q.get_nowait())
                except queue.Empty:
                    pass

                # 2. Concurrency Orchestration tick
                now = time.time()
                if self.is_running and not self.is_paused and (now - last_orchestrate_time >= 0.5):
                    last_orchestrate_time = now
                    self._orchestrate_workers()

            except Exception as e:
                print(f"[EngineManager] Event loop error: {e}")

        # Clean shutdown of the loop
        self._loop.close()

    def _dispatch_event(self, evt):
        kind = evt[0]
        acct_id = evt[1] if len(evt) > 1 else ""
        args = evt[2:] if len(evt) > 2 else ()
        hub = EventHub.instance()
        now = time.time()

        if kind == "log":
            msg = args[0] if len(args) > 0 else ""
            level = args[1] if len(args) > 1 else "info"
            hub.log_emitted.emit(acct_id, msg, level, now)
            try:
                dt_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
                pfx = f"[{acct_id[:8]}]" if acct_id else "[SYSTEM]"
                with open("app.log", "a", encoding="utf-8") as f:
                    f.write(f"[{dt_str}] {pfx} [{level.upper()}] {msg}\n")
            except Exception:
                pass

        elif kind == "status":
            status = args[0] if len(args) > 0 else ""
            sleep_sec = args[1] if len(args) > 1 else None
            accts = {a.id: a for a in self.db.get_accounts()}
            if acct_id in accts:
                a = accts[acct_id]
                a.status = status
                if status == "sleeping" and sleep_sec:
                    a.sleep_until = now + float(sleep_sec)
                elif status != "sleeping":
                    a.sleep_until = 0.0
                self.db.save_account(a)
            hub.account_status_changed.emit(acct_id, status)
            hub.accounts_changed.emit()

            # When an account is put to sleep or enters non-active state, immediately orchestrate replacement
            if status in ("sleeping", "error", "login_expired", "login_required", "stopped", "image_limited", "rate_limited"):
                if self.is_running and not self.is_paused:
                    self._orchestrate_workers()

        elif kind == "finished":
            with self._workers_lock:
                if acct_id in self.workers:
                    del self.workers[acct_id]
            accts = {a.id: a for a in self.db.get_accounts()}
            if acct_id in accts:
                a = accts[acct_id]
                if a.status == "running":
                    a.status = "idle"
                    self.db.save_account(a)
                    hub.account_status_changed.emit(acct_id, "idle")
                    hub.accounts_changed.emit()
            if self.is_running and not self.is_paused:
                self._orchestrate_workers()

        elif kind in ("job_start", "job_done", "job_fail", "job_skip", "job_requeued"):
            stats = self.queue_mgr.stats()
            hub.queue_stats_updated.emit(stats)
            hub.job_event_emitted.emit(kind, acct_id, args[0] if len(args) > 0 else "", args[1] if len(args) > 1 else "")
            hub.queue_changed.emit()

        elif kind == "img_count":
            count = args[0] if len(args) > 0 else 0
            total = args[1] if len(args) > 1 else None
            accts = {a.id: a for a in self.db.get_accounts()}
            if acct_id in accts:
                a = accts[acct_id]
                a.images_session = count
                if total is not None:
                    a.images_total = total
                elif acct_id in self.workers:
                    a.images_total = self.workers[acct_id].account.images_total
                self.db.save_account(a)
                total_val = a.images_total
            else:
                total_val = total or 0
            hub.account_count_updated.emit(acct_id, count, total_val)
            hub.accounts_changed.emit()

    def _orchestrate_workers(self):
        if not self.is_running or self.is_paused:
            return

        hub = EventHub.instance()
        now = time.time()

        with self._workers_lock:
            # 1. Clean up finished workers and reset their account status
            for aid, worker in list(self.workers.items()):
                if not worker.is_running():
                    del self.workers[aid]

            # 2. Check and wake up sleeping accounts whose cooldown expired, and clean up orphaned running accounts
            for a in self.db.get_accounts():
                if a.status == "sleeping":
                    if a.sleep_until <= now or a.sleep_until == 0.0:
                        a.status = "idle"
                        a.sleep_until = 0.0
                        a.images_session = 0
                        self.db.save_account(a)
                        hub.account_status_changed.emit(a.id, "idle")
                        hub.account_count_updated.emit(a.id, 0, a.images_total)
                        hub.accounts_changed.emit()
                        hub.log_emitted.emit(a.id, f"Account [{a.name}] woke up from sleep cooldown.", "info", now)
                elif a.status == "running" and a.id not in self.workers:
                    # Account was marked running in DB but has no active worker
                    a.status = "idle"
                    self.db.save_account(a)
                    hub.account_status_changed.emit(a.id, "idle")
                    hub.accounts_changed.emit()

            # 3. Inactivity Watchdog: detect stuck workers with no progress
            settings = self.db.get_settings()
            inactivity_limit = getattr(settings, "inactive_timeout", 600.0) or 600.0
            for aid, worker in list(self.workers.items()):
                if worker.is_running():
                    try:
                        last_active = worker.get_last_success_time() or worker.get_start_time()
                        if isinstance(last_active, (int, float)) and last_active > 0 and (now - last_active > inactivity_limit):
                            hub.log_emitted.emit(
                                aid,
                                f"Worker [{worker.account.name}] inactive for >{int(inactivity_limit)}s. Restarting stalled worker...",
                                "warning",
                                now
                            )
                            worker.request_stop()
                    except Exception:
                        pass

            # 4. Check active workers vs concurrency limit
            max_parallel = settings.max_parallel_accounts or 1
            active_count = len([w for w in self.workers.values() if w.is_running()])

            # 5. Check queue pending jobs
            stats = self.queue_mgr.stats()
            pending_count = stats.get("pending", 0)

            # If all workers are finished and no pending jobs, batch is done
            if active_count == 0 and pending_count == 0:
                self.is_running = False
                hub.engine_state_changed.emit(False)
                hub.log_emitted.emit("system", "Batch processing complete — all queue jobs finished.", "success", now)
                return

            # 6. Launch additional workers if under concurrency limit
            slots_needed = max_parallel - active_count
            if slots_needed > 0 and pending_count > 0:
                running_ids = set(self.workers.keys())
                accounts = self.db.get_accounts()

                # Stable deterministic order for all enabled accounts
                all_enabled = [a for a in accounts if a.enabled]
                all_enabled.sort(key=lambda a: a.id)

                if all_enabled:
                    n = len(all_enabled)
                    # Start scanning strictly after the last selected account to maintain rotation
                    start_idx = 0
                    if self._last_selected_account_id:
                        for idx, a in enumerate(all_enabled):
                            if a.id == self._last_selected_account_id:
                                start_idx = (idx + 1) % n
                                break

                    characters = {c.name: c for c in self.db.get_characters()}
                    launched = 0

                    for offset in range(n):
                        if launched >= slots_needed:
                            break
                        cand_idx = (start_idx + offset) % n
                        candidate = all_enabled[cand_idx]

                        if (candidate.id not in running_ids
                                and candidate.status in ("idle", "")
                                and (candidate.sleep_until <= now or candidate.sleep_until == 0.0)):
                            worker = AccountWorker(
                                account=candidate,
                                queue_mgr=self.queue_mgr,
                                settings=settings,
                                evt_q=self.evt_q,
                                characters=characters
                            )
                            self.workers[candidate.id] = worker
                            worker.start()
                            self._last_selected_account_id = candidate.id
                            launched += 1
                            hub.log_emitted.emit(
                                candidate.id,
                                f"Profile [{candidate.name}] started (round-robin #{cand_idx+1}/{n}, active {len(self.workers)}/{max_parallel})",
                                "info",
                                now
                            )
                            if launched < slots_needed:
                                start_delay = getattr(settings, "account_start_delay", 1.5) or 1.5
                                if start_delay > 0:
                                    time.sleep(start_delay)

    def start_batch(self, parallel_count: Optional[int] = None):
        settings = self.db.get_settings()
        if parallel_count is not None and parallel_count > 0:
            settings.max_parallel_accounts = parallel_count
            self.db.save_settings(settings)

        now = time.time()
        # Wake up any expired sleeping accounts and reset orphaned running accounts
        for a in self.db.get_accounts():
            if a.status == "sleeping" and (a.sleep_until <= now or a.sleep_until == 0.0):
                a.status = "idle"
                a.sleep_until = 0.0
                a.images_session = 0
                self.db.save_account(a)
            elif a.status == "running" and a.id not in self.workers:
                a.status = "idle"
                self.db.save_account(a)

        accounts = [a for a in self.db.get_accounts() if a.enabled]
        if not accounts:
            EventHub.instance().log_emitted.emit("system", "No enabled accounts configured", "error", time.time())
            return False

        self.is_running = True
        self.is_paused = False
        EventHub.instance().engine_state_changed.emit(True)

        self._orchestrate_workers()
        return True

    def stop_batch(self):
        self.is_running = False
        self.is_paused = False
        EventHub.instance().engine_state_changed.emit(False)
        with self._workers_lock:
            for acct_id, worker in list(self.workers.items()):
                try:
                    worker.request_stop()
                except Exception:
                    pass
            self.workers.clear()

        # Reset all running accounts in database and notify UI
        hub = EventHub.instance()
        for a in self.db.get_accounts():
            if a.status == "running":
                a.status = "idle"
                self.db.save_account(a)
                hub.account_status_changed.emit(a.id, "idle")
        hub.accounts_changed.emit()

    def pause_batch(self):
        self.is_paused = True
        with self._workers_lock:
            for worker in self.workers.values():
                worker.request_pause()

    def resume_batch(self):
        self.is_paused = False
        with self._workers_lock:
            for worker in self.workers.values():
                worker.request_resume()
        if self.is_running:
            self._orchestrate_workers()

    def skip_job(self, account_id: str):
        with self._workers_lock:
            if account_id in self.workers:
                self.workers[account_id].request_skip()

    def reset_account_sleep(self, account_id: str):
        hub = EventHub.instance()
        now = time.time()
        accts = {a.id: a for a in self.db.get_accounts()}
        if account_id in accts:
            a = accts[account_id]
            a.status = "idle"
            a.sleep_until = 0.0
            a.images_session = 0
            a.error_message = ""
            self.db.save_account(a)
            hub.account_status_changed.emit(a.id, "idle")
            hub.account_count_updated.emit(a.id, 0, a.images_total)
            hub.accounts_changed.emit()
            hub.log_emitted.emit(a.id, f"Account [{a.name}] sleep reset — marked free/idle.", "info", now)
            if self.is_running and not self.is_paused:
                self._orchestrate_workers()

    def reset_all_sleeping_accounts(self) -> int:
        hub = EventHub.instance()
        now = time.time()
        count = 0
        for a in self.db.get_accounts():
            if a.status == "sleeping" or (a.sleep_until and a.sleep_until > now):
                a.status = "idle"
                a.sleep_until = 0.0
                a.images_session = 0
                a.error_message = ""
                self.db.save_account(a)
                hub.account_status_changed.emit(a.id, "idle")
                hub.account_count_updated.emit(a.id, 0, a.images_total)
                hub.log_emitted.emit(a.id, f"Account [{a.name}] sleep reset — marked free/idle.", "info", now)
                count += 1
        if count > 0:
            hub.accounts_changed.emit()
            if self.is_running and not self.is_paused:
                self._orchestrate_workers()
        return count

    def stop_engine(self):
        self._stop_poll_evt.set()
        self.stop_batch()


class EngineManager:
    _instance = None

    def __init__(self):
        state = AppState.instance()
        self.engine_thread = EngineThread(state.db, state.queue_mgr)

    @classmethod
    def instance(cls) -> "EngineManager":
        if cls._instance is None:
            cls._instance = EngineManager()
        return cls._instance

    def start_engine(self):
        self.engine_thread.start()

    def stop_engine(self):
        self.engine_thread.stop_engine()
        self.engine_thread.quit()
        self.engine_thread.wait()

    def start_batch(self, parallel_count: Optional[int] = None):
        return self.engine_thread.start_batch(parallel_count)

    def stop_batch(self):
        self.engine_thread.stop_batch()

    def pause_batch(self):
        self.engine_thread.pause_batch()

    def resume_batch(self):
        self.engine_thread.resume_batch()

    def skip_job(self, account_id: str):
        self.engine_thread.skip_job(account_id)

    def reset_account_sleep(self, account_id: str):
        self.engine_thread.reset_account_sleep(account_id)

    def reset_all_sleeping_accounts(self) -> int:
        return self.engine_thread.reset_all_sleeping_accounts()