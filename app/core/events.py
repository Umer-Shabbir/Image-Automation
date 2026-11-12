from PySide6.QtCore import QObject, Signal

class EventHub(QObject):
    _instance = None

    # Global UI Signals
    accounts_changed = Signal()
    characters_changed = Signal()
    settings_changed = Signal()
    queue_changed = Signal()

    # Engine Event Signals
    log_emitted = Signal(str, str, str, float)  # account_id, message, level, time
    queue_stats_updated = Signal(dict)
    account_status_changed = Signal(str, str) # account_id, status
    account_count_updated = Signal(str, int, int) # account_id, session_count, total_count
    job_event_emitted = Signal(str, str, str, str) # kind, account_id, job_id, detail
    engine_state_changed = Signal(bool) # is_running

    @classmethod
    def instance(cls) -> "EventHub":
        if cls._instance is None:
            cls._instance = EventHub()
        return cls._instance