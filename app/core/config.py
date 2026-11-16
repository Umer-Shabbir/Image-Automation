"""
Core configuration and runtime environment manager for Image Automation.
Handles dynamic path resolution, environment loading (.env), and runtime self-healing.
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

# Project root: directory containing main.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_environment(env_file: Optional[Path] = None) -> None:
    """
    Loads environment variables from .env if present.
    Uses python-dotenv if installed, with a robust built-in fallback parser.
    """
    env_path = env_file or (PROJECT_ROOT / ".env")
    if not env_path.exists():
        return

    try:
        import dotenv
        dotenv.load_dotenv(dotenv_path=env_path)
        return
    except ImportError:
        pass

    # Built-in lightweight fallback parser
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        print(f"[Warning] Failed reading .env file: {e}", file=sys.stderr)


# Load environment variables immediately on module import
load_environment()

# Dynamic Paths & Config (resolves relative to PROJECT_ROOT by default)
DB_PATH = os.getenv("DB_PATH", os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "gpt_batch.db")))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "output"))
PROFILES_DIR = os.getenv("PROFILES_DIR", str(PROJECT_ROOT / "profiles"))
LOG_DIR = os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs"))
LOG_FILE = os.getenv("LOG_FILE", str(Path(LOG_DIR) / "app.log"))

FLOW_URL = os.getenv("FLOW_URL", "https://flow.google.com")
BULK_APP_URL = os.getenv("BULK_APP_URL", "https://gemini.google.com/share/79e5de5150e6")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", os.getenv("VALIDATION_API_KEY", ""))
VALIDATION_MODEL = os.getenv("VALIDATION_MODEL", "claude-3-haiku-20240307")
PRESETS_REGISTRY_PATH = os.getenv("PRESETS_REGISTRY_PATH", os.getenv("PRESETS_PATH", ""))
CHROME_PATH = os.getenv("CHROME_PATH", os.getenv("BROWSER_PATH", ""))


def ensure_runtime_directories() -> None:
    """
    Runtime self-healing: ensures all required runtime folders exist on disk
    so fresh clones never crash due to missing directory structures.
    """
    dirs = [
        Path(OUTPUT_DIR),
        Path(PROFILES_DIR),
        Path(LOG_DIR),
        Path(LOG_FILE).parent,
    ]
    if DB_PATH and DB_PATH != ":memory:":
        dirs.append(Path(DB_PATH).parent)

    for d in dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[Warning] Could not initialize directory '{d}': {e}", file=sys.stderr)


def get_profile_dir(account_id: str) -> Path:
    """
    Returns the resolved, guaranteed-to-exist profile directory for a specific account.
    """
    pdir = Path(PROFILES_DIR) / str(account_id)
    pdir.mkdir(parents=True, exist_ok=True)
    return pdir
