import unittest
from datetime import datetime
from models import Job, JobStatus, Account, Workspace, Settings
from queue_manager import QueueManager
from database import Database
import os

class TestCoreModules(unittest.TestCase):
    def setUp(self):
        # Create an in-memory SQLite DB by modifying the path or a temporary file.
        self.test_db_path = "test_batch.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

        self.db = Database(self.test_db_path)
        self.qm = QueueManager(self.db)
        self.qm.load()

    def tearDown(self):
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def test_job_model_clone(self):
        job = Job(topic_name="Test Topic", prompt_text="A cute dog")
        job2 = job.clone()

        self.assertIsNot(job, job2)
        self.assertEqual(job.id, job2.id)
        self.assertEqual(job.topic_name, job2.topic_name)

        job2.status = JobStatus.DONE
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job2.status, JobStatus.DONE)

    def test_queue_manager_add_and_retrieve(self):
        jobs = [
            Job(global_index=0, status=JobStatus.PENDING),
            Job(global_index=1, status=JobStatus.DONE),
            Job(global_index=2, status=JobStatus.PENDING)
        ]

        self.qm.add_jobs(jobs)

        self.assertEqual(self.qm.stats()["total"], 3)
        self.assertEqual(self.qm.stats()["pending"], 2)

        # Test fetching jobs (should only get PENDING in order)
        next_job = self.qm.get_next_job()
        self.assertIsNotNone(next_job)
        self.assertEqual(next_job.global_index, 0)
        self.assertEqual(next_job.status, JobStatus.RUNNING)

        next_job2 = self.qm.get_next_job()
        self.assertIsNotNone(next_job2)
        self.assertEqual(next_job2.global_index, 2)

        # No more jobs
        next_job3 = self.qm.get_next_job()
        self.assertIsNone(next_job3)

        self.assertEqual(self.qm.stats()["running"], 2)
        self.assertEqual(self.qm.stats()["pending"], 0)

    def test_queue_manager_update(self):
        jobs = [Job(global_index=0, status=JobStatus.PENDING)]
        self.qm.add_jobs(jobs)

        job = self.qm.get_next_job()
        job.status = JobStatus.DONE
        job.file_path = "output/test.png"

        self.qm.update_job(job)

        stats = self.qm.stats()
        self.assertEqual(stats["done"], 1)
        self.assertEqual(stats["running"], 0)

        all_jobs = self.qm.all_jobs()
        self.assertEqual(all_jobs[0].file_path, "output/test.png")

    def test_queue_manager_thread_safety_mutations(self):
        # We ensure get_next_job returning a clone means modifying the
        # returned instance doesn't instantly mutate the underlying QueueManager
        # instance until explicitly passed back via update_job
        jobs = [Job(topic_name="Safe Context")]
        self.qm.add_jobs(jobs)

        job = self.qm.get_next_job()
        job.status = JobStatus.DONE

        internal_job = self.qm.all_jobs()[0]
        # Should still be RUNNING internally until update_job is called
        self.assertEqual(internal_job.status, JobStatus.RUNNING)

if __name__ == "__main__":
    unittest.main()
