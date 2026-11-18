"""
Google Flow Studio Batch Pro — Image Automation
Main entry point. Run: python main.py
"""

import sys
import os

def main():
    # ── Universal UTF-8 console output ────────────────────────────────────────
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    # ── Handle CLI options before GUI initialization ──────────────────────────
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python main.py [OPTIONS]")
        print("")
        print("Options:")
        print("  --check, --dry-run   Perform runtime environment & self-healing checks then exit.")
        print("  --help, -h           Show this help message and exit.")
        sys.exit(0)

    # ── Initialize environment & runtime directories ──────────────────────────
    from app.core.config import ensure_runtime_directories, load_environment, DB_PATH
    load_environment()
    ensure_runtime_directories()

    if "--check" in sys.argv or "--dry-run" in sys.argv:
        print("[✓] Runtime directories verified and created.")
        from app.core.app_state import AppState
        state = AppState.instance()
        state.initialize()
        print(f"[✓] Database connection and schema verified at: {state.db.db_path}")
        print("[✓] Queue manager restored cleanly.")
        state.shutdown()
        print("[✓] All startup sanity checks passed successfully.")
        sys.exit(0)

    # ── Qt6 high-DPI
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPalette, QColor

    app = QApplication(sys.argv)
    app.setApplicationName("Image Automation")
    app.setApplicationVersion("6.0.0")
    app.setOrganizationName("FlowStudioBatch")

    # ── Initialize app state ──────────────────────────────────────────────────
    from app.core.app_state import AppState
    state = AppState.instance()
    state.initialize()

    # ── Initialize engine orchestrator ────────────────────────────────────────
    from app.core.engine import EngineManager
    engine = EngineManager.instance()
    engine.start_engine()

    # ── Apply dark theme ──────────────────────────────────────────────────────
    from app.gui.theme import get_stylesheet
    app.setStyleSheet(get_stylesheet())

    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor("#0f0f17"))
    palette.setColor(QPalette.WindowText,      QColor("#e8e8f0"))
    palette.setColor(QPalette.Base,            QColor("#1a1a2e"))
    palette.setColor(QPalette.AlternateBase,   QColor("#1e1e32"))
    palette.setColor(QPalette.Text,            QColor("#e8e8f0"))
    palette.setColor(QPalette.Button,          QColor("#1e1e32"))
    palette.setColor(QPalette.ButtonText,      QColor("#e8e8f0"))
    palette.setColor(QPalette.Highlight,       QColor("#6c63ff"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Link,            QColor("#a89fff"))
    palette.setColor(QPalette.ToolTipBase,     QColor("#1e1e32"))
    palette.setColor(QPalette.ToolTipText,     QColor("#e8e8f0"))
    palette.setColor(QPalette.PlaceholderText, QColor("#5a5a7a"))
    app.setPalette(palette)

    # ── Launch main window ────────────────────────────────────────────────────
    from app.gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    exit_code = app.exec()
    engine.stop_engine()
    state.shutdown()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()