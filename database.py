# database.py  v6.0
"""
Thread-safe, leak-free SQLite persistence layer with WAL mode.
Supports Accounts, Jobs, Characters, and Settings persistence for Google Flow.
"""

import sqlite3
import json
from contextlib import contextmanager
from typing import List
from models import Account, Job, Settings, Workspace, Character

DB_PATH = "gpt_batch.db"


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init()

    @contextmanager
    def get_connection(self):
        """
        Yield a configured sqlite3 connection and guarantee closing on exit.
        Uses WAL journal mode and a generous busy timeout to prevent concurrency lockouts.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init(self):
        with self.get_connection() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT DEFAULT '',
                    password TEXT DEFAULT '',
                    color TEXT DEFAULT '#4285F4',
                    enabled INTEGER DEFAULT 1,
                    workspaces TEXT DEFAULT '[]',
                    current_workspace_idx INTEGER DEFAULT 0,
                    images_session INTEGER DEFAULT 0,
                    images_total INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'idle',
                    error_message TEXT DEFAULT '',
                    sleep_until REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS characters (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    prompt_tag TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    reference_image_paths TEXT DEFAULT '[]',
                    voice_name TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 1,
                    created_at REAL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    topic_name TEXT,
                    topic_slug TEXT,
                    topic_index INTEGER,
                    prompt_text TEXT,
                    prompt_index INTEGER,
                    global_index INTEGER,
                    prompt_slug TEXT,
                    status TEXT DEFAULT 'pending',
                    image_url TEXT DEFAULT '',
                    file_path TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    assigned_account_id TEXT DEFAULT '',
                    created_at REAL,
                    started_at REAL DEFAULT 0,
                    completed_at REAL DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    character_name TEXT DEFAULT '',
                    model_name TEXT DEFAULT 'Nano Banana',
                    mode TEXT DEFAULT 'image',
                    aspect_ratio TEXT DEFAULT '16:9',
                    project_folder TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_global_index ON jobs(global_index);
            """)

            # Schema migration check for new job columns
            for col, default in [
                ("character_name", "''"),
                ("model_name", "'Nano Banana'"),
                ("mode", "'image'"),
                ("aspect_ratio", "'16:9'"),
                ("project_folder", "''")
            ]:
                try:
                    c.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT DEFAULT {default}")
                except Exception:
                    pass

    # ── Characters ────────────────────────────────────────────────────────────

    def _row_to_character(self, row: sqlite3.Row) -> Character:
        try:
            image_paths = json.loads(row["reference_image_paths"] or "[]")
        except Exception:
            image_paths = []
        return Character(
            id=row["id"],
            name=row["name"] or "New Character",
            prompt_tag=row["prompt_tag"] or "",
            description=row["description"] or "",
            reference_image_paths=image_paths,
            voice_name=row["voice_name"] or "",
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or 0.0,
        )

    def get_characters(self) -> List[Character]:
        with self.get_connection() as c:
            rows = c.execute("SELECT * FROM characters ORDER BY created_at DESC").fetchall()
        return [self._row_to_character(r) for r in rows]

    def save_character(self, char: Character):
        paths_json = json.dumps(char.reference_image_paths)
        with self.get_connection() as c:
            c.execute("""
                INSERT OR REPLACE INTO characters
                (id, name, prompt_tag, description, reference_image_paths, voice_name, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                char.id, char.name, char.prompt_tag, char.description,
                paths_json, char.voice_name, int(char.is_active), char.created_at
            ))

    def delete_character(self, char_id: str):
        with self.get_connection() as c:
            c.execute("DELETE FROM characters WHERE id = ?", (char_id,))

    # ── Accounts ──────────────────────────────────────────────────────────────

    def _ws_to_json(self, ws_list: List[Workspace]) -> str:
        return json.dumps([w.to_dict() for w in ws_list])

    def _row_to_account(self, row: sqlite3.Row) -> Account:
        try:
            ws_data = json.loads(row["workspaces"] or "[]")
            workspaces = [Workspace.from_dict(w) for w in ws_data] or [Workspace()]
        except Exception:
            workspaces = [Workspace()]
        try:
            password = row["password"] or ""
        except Exception:
            password = ""
        try:
            color = row["color"] or "#4285F4"
        except Exception:
            color = "#4285F4"
        try:
            sleep_until = float(row["sleep_until"] or 0.0)
        except Exception:
            sleep_until = 0.0

        return Account(
            id=row["id"],
            name=row["name"],
            email=row["email"] or "",
            password=password,
            color=color,
            enabled=bool(row["enabled"]),
            workspaces=workspaces,
            current_workspace_idx=row["current_workspace_idx"] or 0,
            images_session=row["images_session"] or 0,
            images_total=row["images_total"] or 0,
            status=row["status"] or "idle",
            error_message=row["error_message"] or "",
            sleep_until=sleep_until,
        )

    def get_accounts(self) -> List[Account]:
        with self.get_connection() as c:
            rows = c.execute("SELECT * FROM accounts ORDER BY name").fetchall()
        return [self._row_to_account(r) for r in rows]

    def save_account(self, a: Account):
        ws_json = self._ws_to_json(a.workspaces)
        with self.get_connection() as c:
            for col, default in [("password", "''"), ("color", "'#4285F4'"), ("sleep_until", "0")]:
                try:
                    c.execute(f"ALTER TABLE accounts ADD COLUMN {col} TEXT DEFAULT {default}")
                except Exception:
                    pass

            c.execute("""
                INSERT OR REPLACE INTO accounts
                (id, name, email, password, color, enabled, workspaces, current_workspace_idx,
                 images_session, images_total, status, error_message, sleep_until)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                a.id, a.name, a.email, a.password, a.color, int(a.enabled),
                ws_json, a.current_workspace_idx, a.images_session,
                a.images_total, a.status, a.error_message, a.sleep_until
            ))

    def delete_account(self, account_id: str):
        with self.get_connection() as c:
            c.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    def reset_account_sleep(self, account_id: str):
        with self.get_connection() as c:
            c.execute("UPDATE accounts SET status = 'idle', sleep_until = 0.0, images_session = 0, error_message = '' WHERE id = ?", (account_id,))

    def reset_all_sleeping_accounts(self) -> int:
        with self.get_connection() as c:
            cur = c.execute("UPDATE accounts SET status = 'idle', sleep_until = 0.0, images_session = 0 WHERE status = 'sleeping' OR sleep_until > 0")
            return cur.rowcount

    # ── Jobs ──────────────────────────────────────────────────────────────────

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        char_name = row["character_name"] if "character_name" in row.keys() else ""
        model_name = row["model_name"] if "model_name" in row.keys() else "Nano Banana"
        mode = row["mode"] if "mode" in row.keys() else "image"
        ar = row["aspect_ratio"] if "aspect_ratio" in row.keys() else "16:9"

        return Job(
            id=row["id"],
            topic_name=row["topic_name"] or "",
            topic_slug=row["topic_slug"] or "",
            topic_index=row["topic_index"] or 0,
            prompt_text=row["prompt_text"] or "",
            prompt_index=row["prompt_index"] or 0,
            global_index=row["global_index"] or 0,
            prompt_slug=row["prompt_slug"] or "",
            status=row["status"] or "pending",
            image_url=row["image_url"] or "",
            file_path=row["file_path"] or "",
            error=row["error"] or "",
            assigned_account_id=row["assigned_account_id"] or "",
            created_at=row["created_at"] or 0.0,
            started_at=row["started_at"] or 0.0,
            completed_at=row["completed_at"] or 0.0,
            retry_count=row["retry_count"] or 0,
            character_name=char_name or "",
            model_name=model_name or "Nano Banana",
            mode=mode or "image",
            aspect_ratio=ar or "16:9",
            project_folder=row["project_folder"] if "project_folder" in row.keys() else ""
        )

    def get_jobs(self) -> List[Job]:
        with self.get_connection() as c:
            rows = c.execute("SELECT * FROM jobs ORDER BY global_index").fetchall()
        return [self._row_to_job(r) for r in rows]

    def save_job(self, job: Job):
        with self.get_connection() as c:
            c.execute("""
                INSERT OR REPLACE INTO jobs
                (id, topic_name, topic_slug, topic_index, prompt_text, prompt_index,
                 global_index, prompt_slug, status, image_url, file_path, error,
                 assigned_account_id, created_at, started_at, completed_at, retry_count,
                 character_name, model_name, mode, aspect_ratio, project_folder)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.id, job.topic_name, job.topic_slug, job.topic_index,
                job.prompt_text, job.prompt_index, job.global_index, job.prompt_slug,
                job.status, job.image_url, job.file_path, job.error,
                job.assigned_account_id, job.created_at, job.started_at,
                job.completed_at, job.retry_count,
                job.character_name, job.model_name, job.mode, job.aspect_ratio, job.project_folder
            ))

    def save_jobs_bulk(self, jobs: List[Job]):
        if not jobs:
            return
        with self.get_connection() as c:
            data = [
                (
                    j.id, j.topic_name, j.topic_slug, j.topic_index,
                    j.prompt_text, j.prompt_index, j.global_index, j.prompt_slug,
                    j.status, j.image_url, j.file_path, j.error,
                    j.assigned_account_id, j.created_at, j.started_at,
                    j.completed_at, j.retry_count,
                    j.character_name, j.model_name, j.mode, j.aspect_ratio, j.project_folder
                )
                for j in jobs
            ]
            c.executemany("""
                INSERT OR REPLACE INTO jobs
                (id, topic_name, topic_slug, topic_index, prompt_text, prompt_index,
                 global_index, prompt_slug, status, image_url, file_path, error,
                 assigned_account_id, created_at, started_at, completed_at, retry_count,
                 character_name, model_name, mode, aspect_ratio, project_folder)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)

    def clear_jobs(self):
        with self.get_connection() as c:
            c.execute("DELETE FROM jobs")

    def reset_failed_jobs(self):
        with self.get_connection() as c:
            c.execute("UPDATE jobs SET status = 'pending', error = '', retry_count = 0 WHERE status IN ('failed', 'skipped')")

    def recover_interrupted_jobs(self) -> int:
        with self.get_connection() as c:
            cur = c.execute("UPDATE jobs SET status = 'pending', assigned_account_id = '' WHERE status = 'running'")
            count = cur.rowcount
            c.execute("UPDATE accounts SET status = 'idle' WHERE status = 'running'")
            return count

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> Settings:
        with self.get_connection() as c:
            rows = c.execute("SELECT key, value FROM settings").fetchall()
        data = {}
        for r in rows:
            try:
                data[r["key"]] = json.loads(r["value"])
            except Exception:
                pass
        s = Settings()
        for k, v in data.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s

    def save_settings(self, s: Settings):
        with self.get_connection() as c:
            items = [(k, json.dumps(v)) for k, v in s.__dict__.items()]
            c.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", items)

    def get_queue_stats(self) -> dict:
        with self.get_connection() as c:
            total   = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            done    = c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'done'").fetchone()[0]
            failed  = c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'failed'").fetchone()[0]
            skipped = c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'skipped'").fetchone()[0]
            running = c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'running'").fetchone()[0]
            pending = c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'pending'").fetchone()[0]
        return {
            "total": total,
            "done": done,
            "failed": failed,
            "skipped": skipped,
            "running": running,
            "pending": pending
        }
