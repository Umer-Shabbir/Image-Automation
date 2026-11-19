# Google Flow Studio Batch Pro — Image Automation

An automated batch generation and workflow orchestration suite for Google Flow and Gemini Canvas media creation, featuring character consistency tagging, multi-account concurrency orchestration, persistent session handling, and automated quality validation.

---

## Prerequisites

- **Python**: `3.10` or higher (Python 3.12 recommended)
- **Git**: Installed and available on your PATH
- **Playwright Chromium**: Required for browser automation (installed via CLI during setup)
- **Supported Operating Systems**: Windows 10/11, macOS (12+), and Linux (Ubuntu 20.04+, Debian 11+, Fedora)

---

## Quick Start (Fresh Clone)

### Windows (PowerShell)

```powershell
# 1. Navigate into the cloned repository
cd "Image Automation"

# 2. Configure local environment file
Copy-Item .env.example .env

# 3. Create and activate a Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Playwright browser binaries
playwright install chromium

# 6. Run headless startup check (verifies database, schema, and paths)
python main.py --check

# 7. Launch the application
python main.py
# (Alternative: use .\run.ps1 or run.bat)
```

### Linux & macOS (Bash / Zsh)

```bash
# 1. Navigate into the cloned repository
cd "Image Automation"

# 2. Configure local environment file
cp .env.example .env

# 3. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Playwright browser binaries
playwright install chromium

# 6. Run headless startup check (verifies database, schema, and paths)
python3 main.py --check

# 7. Launch the application
python3 main.py
# (Alternative: chmod +x run.sh && ./run.sh)
```

---

## Environment Variables

All variables are configured in `.env` (copy from `.env.example`). The application provides automatic defaults for every setting and automatically creates runtime directories if they do not exist.

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `FLOW_URL` | Optional | `https://flow.google.com` | Target URL for the Google Flow studio platform. |
| `BULK_APP_URL` | Optional | `https://gemini.google.com/share/79e5de5150e6` | Target URL for the Gemini Canvas Bulk Media Generator app. |
| `DB_PATH` | Optional | `gpt_batch.db` | SQLite database file location (relative to project root or absolute). |
| `OUTPUT_DIR` | Optional | `output` | Target directory where downloaded and generated images/videos are organized. |
| `PROFILES_DIR` | Optional | `profiles` | Base directory storing isolated Chromium user data sessions per account. |
| `LOG_DIR` | Optional | `logs` | Directory for application logs. |
| `LOG_FILE` | Optional | `logs/app.log` | File path for runtime orchestration log output. |
| `PRESETS_REGISTRY_PATH` | Optional | *(empty)* | Custom path to an external `master_presets_registry.json` file. |
| `CHROME_PATH` | Optional | *(empty)* | Custom path to a system-installed Chrome/Brave/Edge binary if not using Playwright's Chromium. |
| `ANTHROPIC_API_KEY` | Optional | *(empty)* | Anthropic API key used for automated image validation via Claude Vision in `validator.py`. |
| `VALIDATION_MODEL` | Optional | `claude-3-haiku-20240307` | Claude model variant utilized during prompt-adherence verification. |

---

## Runtime Self-Healing & Directory Management

The application includes automated self-healing mechanisms so a clean clone on a new machine runs without manual directory provisioning:
- **`output/`**: Created automatically upon startup or when batches run.
- **`profiles/`**: Isolated profile folders (`profiles/<account_id>`) are created on-demand for each registered account.
- **`logs/`**: Created automatically for application-level logs.
- **Database Directory**: If `DB_PATH` points to a subdirectory (e.g., `data/gpt_batch.db`), its parent directory is created automatically with SQLite WAL mode enabled.

---

## Running Verification & Tests

To execute the full test suite and verify system logic:

```bash
# Activate your virtual environment first, then:
pytest
```

To run a headless startup and environment sanity check:

```bash
python main.py --check
```
