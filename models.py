# models.py  v6.0
"""
Domain models and data structures for Google Flow Studio Batch Pro.
Supports Character Consistency, Multi-Model Selection, Image/Video Generation, and Aspect Ratios.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
import time
import uuid

ACCOUNT_COLORS: List[str] = [
    "#4285F4", "#34A853", "#FBBC05", "#EA4335",
    "#8e24aa", "#00acc1", "#f4511e", "#6d4c41",
    "#1565c0", "#2e7d32", "#ad1457", "#558b2f",
]


class FlowModel:
    NANO_BANANA = "Nano Banana"
    IMAGEN_3    = "Imagen 3"
    VEO_3       = "Veo 3"
    VEO_3_1     = "Veo 3.1"
    GEMINI_OMNI = "Gemini Omni"

    ALL = [NANO_BANANA, IMAGEN_3, VEO_3, VEO_3_1, GEMINI_OMNI]


class GenerationPlatform:
    FLOW = "flow"
    BULK_APP = "bulk_app"

    ALL = [FLOW, BULK_APP]


class GenerationMode:
    IMAGE = "image"
    VIDEO = "video"

    ALL = [IMAGE, VIDEO]


class AspectRatio:
    RATIO_16_9 = "16:9"
    RATIO_9_16 = "9:16"
    RATIO_1_1  = "1:1"
    RATIO_4_3  = "4:3"
    RATIO_3_4  = "3:4"
    RATIO_21_9 = "21:9"

    ALL = [RATIO_16_9, RATIO_9_16, RATIO_1_1, RATIO_4_3, RATIO_3_4, RATIO_21_9]

class ImageCount:
    COUNT_1 = "x1"
    COUNT_2 = "x2"
    COUNT_3 = "x3"
    COUNT_4 = "x4"

    ALL = [COUNT_1, COUNT_2, COUNT_3, COUNT_4]


class JobStatus:
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    SKIPPED   = "skipped"

    ALL = {PENDING, RUNNING, DONE, FAILED, SKIPPED}


class AccountStatus:
    IDLE           = "idle"
    RUNNING        = "running"
    PAUSED         = "paused"
    RATE_LIMITED   = "rate_limited"
    IMAGE_LIMITED  = "image_limited"
    INACTIVE       = "inactive"
    ERROR          = "error"
    LOGIN_REQUIRED = "login_required"
    LOGIN_EXPIRED  = "login_expired"
    STOPPED        = "stopped"
    EXHAUSTED      = "exhausted"
    SLEEPING       = "sleeping"

    ALL = {
        IDLE, RUNNING, PAUSED, RATE_LIMITED, IMAGE_LIMITED,
        INACTIVE, ERROR, LOGIN_REQUIRED, LOGIN_EXPIRED, STOPPED, EXHAUSTED, SLEEPING
    }


@dataclass
class Character:
    """Character definition for multi-prompt and multi-scene visual consistency."""
    id:                   str        = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:                 str        = "New Character"
    prompt_tag:           str        = ""
    description:          str        = ""
    reference_image_paths: List[str] = field(default_factory=list)
    voice_name:           str        = ""
    is_active:            bool       = True
    created_at:           float      = field(default_factory=time.time)

    def __post_init__(self):
        if not self.prompt_tag and self.name:
            clean_tag = self.name.replace(" ", "")
            self.prompt_tag = f"@{clean_tag}" if not clean_tag.startswith("@") else clean_tag

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt_tag": self.prompt_tag,
            "description": self.description,
            "reference_image_paths": self.reference_image_paths,
            "voice_name": self.voice_name,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        return cls(
            id=data.get("id") or str(uuid.uuid4())[:8],
            name=data.get("name", "New Character"),
            prompt_tag=data.get("prompt_tag", ""),
            description=data.get("description", ""),
            reference_image_paths=data.get("reference_image_paths") or [],
            voice_name=data.get("voice_name", ""),
            is_active=bool(data.get("is_active", True)),
            created_at=float(data.get("created_at", time.time())),
        )

    def clone(self) -> "Character":
        return Character(
            id=self.id,
            name=self.name,
            prompt_tag=self.prompt_tag,
            description=self.description,
            reference_image_paths=list(self.reference_image_paths),
            voice_name=self.voice_name,
            is_active=self.is_active,
            created_at=self.created_at,
        )


@dataclass
class Workspace:
    id:                 str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:               str   = "Default"
    is_active:          bool  = True
    rate_limited_until: float = 0.0
    image_limit_until:  float = 0.0
    images_generated:   int   = 0
    exhausted:          bool  = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "is_active": self.is_active,
            "rate_limited_until": self.rate_limited_until,
            "image_limit_until": self.image_limit_until,
            "images_generated": self.images_generated,
            "exhausted": self.exhausted,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workspace":
        return cls(
            id=data.get("id") or str(uuid.uuid4())[:8],
            name=data.get("name", "Default"),
            is_active=bool(data.get("is_active", True)),
            rate_limited_until=float(data.get("rate_limited_until", 0.0)),
            image_limit_until=float(data.get("image_limit_until", 0.0)),
            images_generated=int(data.get("images_generated", 0)),
            exhausted=bool(data.get("exhausted", False)),
        )


@dataclass
class Account:
    id:                    str             = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:                  str             = "Google Account"
    email:                 str             = ""
    password:              str             = ""
    color:                 str             = "#4285F4"
    enabled:               bool            = True
    workspaces:            List[Workspace] = field(default_factory=lambda: [Workspace()])
    current_workspace_idx: int             = 0
    images_session:        int             = 0
    images_total:          int             = 0
    current_prompt:        str             = ""
    status:                str             = AccountStatus.IDLE
    error_message:         str             = ""
    last_image_time:       float           = 0.0

    sleep_until:           float           = 0.0

    def current_workspace(self) -> Workspace:
        if self.workspaces and 0 <= self.current_workspace_idx < len(self.workspaces):
            return self.workspaces[self.current_workspace_idx]
        if not self.workspaces:
            self.workspaces = [Workspace()]
            self.current_workspace_idx = 0
        return self.workspaces[0]

    def clone(self) -> "Account":
        return Account(
            id=self.id,
            name=self.name,
            email=self.email,
            password=self.password,
            color=self.color,
            enabled=self.enabled,
            workspaces=[Workspace.from_dict(w.to_dict()) for w in self.workspaces],
            current_workspace_idx=self.current_workspace_idx,
            images_session=self.images_session,
            images_total=self.images_total,
            current_prompt=self.current_prompt,
            status=self.status,
            error_message=self.error_message,
            last_image_time=self.last_image_time,
            sleep_until=self.sleep_until,
        )


@dataclass
class Job:
    id:                  str   = field(default_factory=lambda: str(uuid.uuid4()))
    topic_name:          str   = ""
    topic_slug:          str   = ""
    topic_index:         int   = 0
    prompt_text:         str   = ""
    prompt_index:        int   = 0
    global_index:        int   = 0
    prompt_slug:         str   = ""
    status:              str   = JobStatus.PENDING
    image_url:           str   = ""
    file_path:           str   = ""
    error:               str   = ""
    assigned_account_id: str   = ""
    created_at:          float = field(default_factory=time.time)
    started_at:          float = 0.0
    completed_at:        float = 0.0
    retry_count:         int   = 0
    project_folder:      str   = ""

    # â”€â”€ Google Flow Specifics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    character_name:      str   = ""
    model_name:          str   = FlowModel.NANO_BANANA
    mode:                str   = GenerationMode.IMAGE
    aspect_ratio:          str   = AspectRatio.RATIO_16_9
    image_count:           str   = "x1"
    thumbnail_index:       int   = 0

    def clone(self) -> "Job":
        return Job(
            id=self.id,
            topic_name=self.topic_name,
            topic_slug=self.topic_slug,
            topic_index=self.topic_index,
            prompt_text=self.prompt_text,
            prompt_index=self.prompt_index,
            global_index=self.global_index,
            prompt_slug=self.prompt_slug,
            status=self.status,
            image_url=self.image_url,
            file_path=self.file_path,
            error=self.error,
            assigned_account_id=self.assigned_account_id,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            retry_count=self.retry_count,
            character_name=self.character_name,
            model_name=self.model_name,
            mode=self.mode,
            aspect_ratio=self.aspect_ratio,
            project_folder=self.project_folder,
            image_count=self.image_count,
            thumbnail_index=self.thumbnail_index,
        )


@dataclass
class Settings:
    # â”€â”€ Output â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    output_dir:            str   = "output"
    filename_template:     str   = "{topicSlug}/{topicSlug}_{promptIndex}_{promptSlug}.png"
    max_slug_chars:        int   = 60
    min_image_bytes:       int   = 30_000      # minimum file size sanity check

    # ── Target Platform & URLs ───────────────────────────────────────────────────
    generation_platform:   str   = GenerationPlatform.FLOW  # "flow" or "bulk_app"
    flow_url:              str   = "https://flow.google.com"
    bulk_app_url:          str   = "https://gemini.google.com/share/79e5de5150e6"
    bulk_batch_size:       int   = 10  # number of prompts to batch in bulk platform mode

    # ── Google Flow Generation Controls ──────────────────────────────────────────
    default_model:         str   = FlowModel.NANO_BANANA
    generation_mode:       str   = GenerationMode.IMAGE
    aspect_ratio:          str   = AspectRatio.RATIO_16_9
    image_count:           str   = "x1"
    active_character_id:   str   = ""
    active_character_name: str   = ""
    auto_attach_character: bool  = True

    # ── Queue behaviour ──────────────────────────────────────────────────────────
    shuffle_prompts:       bool  = False        # randomise queue order on load
    new_chat_mode:         str   = "per_topic"  # per_topic | per_prompt | never
    project_refresh_threshold: int = 20         # refresh project / start new project after N generations (0 = disabled)
    auto_workspace_switch: bool  = True

    # ── Prompt modifiers ─────────────────────────────────────────────────────────
    prompt_prefix:         str   = ""
    prompt_suffix:         str   = ""
    style_preset:          str   = ""

    # ── Parallelism & Limits ─────────────────────────────────────────────────────
    max_parallel_accounts: int   = 1
    hard_generation_limit: int   = 0            # 0 = disabled; force sleep once active account reaches N generations
    account_start_delay:   float = 1.5          # seconds between each parallel account start

    # â”€â”€ Job timing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    delay_between_prompts: float = 3.0   # wait between jobs (same account)
    rate_limit_wait:       float = 300.0 # wait after hitting rate limit
    flagged_sleep_time:    float = 1800.0 # wait (30 min) when profile flagged for unusual activity
    retry_delay:           float = 5.0   # wait before a retry attempt

    # â”€â”€ Generation detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    image_stable_time:     float = 6.0   # media must be unchanged this many seconds
    generation_timeout:    float = 420.0 # absolute max time per generation
    response_settle:       float = 1.0   # wait after generation stops before classifying
    download_confirm_wait: float = 2.0   # wait for download button before proceeding anyway
    max_retries:           int   = 3

    # â”€â”€ Polling intervals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    poll_generating:       float = 0.8   # while progress indicator visible
    poll_post_stop:        float = 0.5   # fast poll immediately after generation stops
    poll_stable:           float = 0.8   # poll interval during stability gate
    poll_idle:             float = 1.0   # no action yet

    # Validation settings
    enable_validation:     bool  = False
    validation_api_key:    str   = ''
    validation_model:      str   = 'claude-3-haiku-20240307'

    # ── Browser navigation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    page_load_settle:      float = 2.0   # after page navigation
    new_chat_settle:       float = 1.5   # after opening new project
    ws_switch_settle:      float = 2.5   # after workspace switch
    login_wait_timeout:    float = 150.0 # max seconds to wait for Google login

    # â”€â”€ Human-like typing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    type_wpm:              int   = 85    # words-per-minute target
    type_variance:         float = 0.35  # Â±% random variance per word delay
    type_burst_chance:     float = 0.15  # probability of a short burst (fast run)
    type_pause_chance:     float = 0.10  # probability of a mid-word pause
    type_typo_chance:      float = 0.03  # probability of a typo+correction per word
    mouse_move_steps:      int   = 8     # smoothness of mouse move to input

    # â”€â”€ Action micro-delays â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    click_settle:          float = 0.50  # settle after a click action
    send_poll_interval:    float = 0.30  # poll interval when looking for generate button
    multi_choice_recheck:  float = 1.5   # wait after handling variations
    ws_switch_retry_wait:  float = 2.5   # wait after workspace switch before job retry
    clarification_wait:    float = 1.5   # wait after sending clarification reply
    input_poll_interval:   float = 0.30  # poll interval while waiting for input to appear
    input_confirm_settle:  float = 0.18  # settle after input confirmed visible

    # â”€â”€ Inactive watchdog â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    inactive_timeout:      float = 600.0 # seconds idle before marking inactive
    inactive_max_retries:  int   = 2     # recovery attempts before cycling out

    # â”€â”€ Export / quality â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    save_metadata_json:    bool  = False  # save a .json sidecar with prompt + timestamp
    dedup_check:           bool  = True   # skip job if output file already exists
    auto_open_output:      bool  = False  # open output folder after batch finishes

    # Validation settings
    enable_validation:     bool  = False
    validation_api_key:    str   = ''
    validation_model:      str   = 'claude-3-haiku-20240307'

    # ── Browser â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    headless:              bool  = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

