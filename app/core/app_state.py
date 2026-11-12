import os
import sys

# Ensure root path is accessible to load core modules correctly
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from database import Database
from queue_manager import QueueManager

class AppState:
    _instance = None

    def __init__(self):
        self.db: Database = None
        self.queue_mgr: QueueManager = None

    @classmethod
    def instance(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = AppState()
        return cls._instance

    def initialize(self):
        self.db = Database('gpt_batch.db')
        self.queue_mgr = QueueManager(self.db)
        self.queue_mgr.load()

        import time
        now = time.time()
        for a in self.db.get_accounts():
            if a.status == "running":
                a.status = "idle"
                self.db.save_account(a)
            elif a.status == "sleeping" and (a.sleep_until <= now or a.sleep_until == 0.0):
                a.status = "idle"
                a.sleep_until = 0.0
                a.images_session = 0
                self.db.save_account(a)

    def shutdown(self):
        # Graceful cleanup if needed
        pass