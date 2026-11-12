# queue_manager.py  v5.5
"""
Thread-safe, O(1) in-memory sync for the Image Automation Job queue.
Modified to decouple Job references explicitly across threads and remove loop iteration bottlenecks.
"""

import threading
from typing import List, Optional, Dict
from models import Job, JobStatus
from database import Database


class QueueManager:
    def __init__(self, db: Database):
        self._db = db
        self._lock = threading.Lock()

        self._jobs_by_id: Dict[str, Job] = {}
        self._jobs_idx_by_id: Dict[str, int] = {}
        self._jobs_ordered: List[Job] = []

        # O(1) cursor logic replaces linear O(N) array scans
        self._pending_idx: int = 0

    def load(self):
        """Restore queue from database. Recovers any crash-interrupted jobs."""
        with self._lock:
            self._db.recover_interrupted_jobs()
            jobs = self._db.get_jobs()

            self._jobs_ordered = jobs
            self._jobs_by_id = {j.id: j for j in jobs}
            self._jobs_idx_by_id = {j.id: idx for idx, j in enumerate(jobs)}

            self._pending_idx = 0
            # Pre-calc first valid pending
            self._advance_pending_cursor()

    def _advance_pending_cursor(self):
        """Internal pointer helper to fast-forward past completed constraints."""
        while self._pending_idx < len(self._jobs_ordered):
            if self._jobs_ordered[self._pending_idx].status == JobStatus.PENDING:
                break
            self._pending_idx += 1

    def add_jobs(self, jobs: List[Job], append: bool = True):
        with self._lock:
            if not append:
                self._jobs_ordered.clear()
                self._jobs_by_id.clear()
                self._jobs_idx_by_id.clear()
                self._pending_idx = 0
                self._db.clear_jobs()

            # Persist bulk transaction first
            self._db.save_jobs_bulk(jobs)

            for j in jobs:
                self._jobs_idx_by_id[j.id] = len(self._jobs_ordered)
                self._jobs_ordered.append(j)
                self._jobs_by_id[j.id] = j

            self._advance_pending_cursor()

    def get_next_job(self) -> Optional[Job]:
        """O(1) pending job retrieval."""
        with self._lock:
            self._advance_pending_cursor()

            if self._pending_idx < len(self._jobs_ordered):
                j = self._jobs_ordered[self._pending_idx]
                j.status = JobStatus.RUNNING
                self._db.save_job(j)

                # Advance cursor past this now-running job
                self._pending_idx += 1

                # Return a separate copy to avoid cross-thread mutations hitting the UI thread simultaneously
                return j.clone()

        return None

    def get_next_jobs(self, max_count: int = 10, same_project_only: bool = True) -> List[Job]:
        """
        Retrieves a batch of up to `max_count` pending jobs atomically.
        If `same_project_only` is True, only batches jobs that belong to the same project folder/topic
        to prevent cross-project mixing.
        """
        with self._lock:
            self._advance_pending_cursor()
            if self._pending_idx >= len(self._jobs_ordered):
                return []

            batch: List[Job] = []
            first_job = self._jobs_ordered[self._pending_idx]
            target_project = getattr(first_job, "project_folder", "")
            target_topic = getattr(first_job, "topic_name", "")

            curr_idx = self._pending_idx
            while curr_idx < len(self._jobs_ordered) and len(batch) < max_count:
                cand = self._jobs_ordered[curr_idx]
                if cand.status == JobStatus.PENDING:
                    if same_project_only and (target_project or target_topic):
                        cand_proj = getattr(cand, "project_folder", "")
                        cand_topic = getattr(cand, "topic_name", "")
                        if target_project and cand_proj != target_project:
                            curr_idx += 1
                            continue
                        elif not target_project and cand_topic != target_topic:
                            curr_idx += 1
                            continue

                    cand.status = JobStatus.RUNNING
                    self._db.save_job(cand)
                    batch.append(cand.clone())
                curr_idx += 1

            self._advance_pending_cursor()
            return batch

    def update_job(self, job: Job):
        """Update internal job cache and trigger DB sync. Received clone writes back to main state."""
        with self._lock:
            self._db.save_job(job)

            if job.id in self._jobs_by_id:
                target = self._jobs_by_id[job.id]

                # Apply diff natively to the managed object
                target.status = job.status
                target.error = job.error
                target.file_path = job.file_path
                target.image_url = job.image_url
                target.started_at = job.started_at
                target.completed_at = job.completed_at
                target.retry_count = job.retry_count
                target.assigned_account_id = job.assigned_account_id

                # If job reverted to pending (e.g. rate limit wait unspooled)
                # we must recalculate the pending cursor negatively
                if target.status == JobStatus.PENDING:
                    target_idx = self._jobs_idx_by_id.get(job.id, self._pending_idx)
                    if target_idx < self._pending_idx:
                        self._pending_idx = target_idx

    def all_jobs(self) -> List[Job]:
        """Provides a safe snapshot sequence of all jobs."""
        with self._lock:
            # We clone the list structurally. The Jobs inside are safe for Tkinter to read (read-only render layer)
            return list(self._jobs_ordered)

    def has_pending(self) -> bool:
        """Returns True if there is incomplete work (PENDING or RUNNING). O(1) via constraints."""
        with self._lock:
            if self._pending_idx < len(self._jobs_ordered):
                return True
            # Running jobs count as pending for active worker limits
            return any(j.status == JobStatus.RUNNING for j in self._jobs_ordered)

    def retry_failed(self):
        with self._lock:
            self._db.reset_failed_jobs()

            # Reset properties manually in RAM and rewind cursor
            rewound = False
            for idx, j in enumerate(self._jobs_ordered):
                if j.status in (JobStatus.FAILED, JobStatus.SKIPPED):
                    j.status = JobStatus.PENDING
                    j.error = ""
                    j.retry_count = 0

                    if not rewound or idx < self._pending_idx:
                        self._pending_idx = idx
                        rewound = True

    def clear(self):
        with self._lock:
            self._jobs_ordered.clear()
            self._jobs_by_id.clear()
            self._jobs_idx_by_id.clear()
            self._pending_idx = 0
            self._db.clear_jobs()

    def stats(self) -> dict:
        with self._lock:
            total = len(self._jobs_ordered)

            counts = {
                JobStatus.DONE: 0,
                JobStatus.FAILED: 0,
                JobStatus.SKIPPED: 0,
                JobStatus.RUNNING: 0,
                JobStatus.PENDING: 0,
            }

            for j in self._jobs_ordered:
                counts[j.status] = counts.get(j.status, 0) + 1

        return {
            "total": total,
            "done": counts[JobStatus.DONE],
            "failed": counts[JobStatus.FAILED],
            "skipped": counts[JobStatus.SKIPPED],
            "running": counts[JobStatus.RUNNING],
            "pending": counts[JobStatus.PENDING],
        }
