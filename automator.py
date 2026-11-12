# automator.py  v6.0
"""
Google Flow Automation Engine â€” v6.0

Automates Google Flow (https://flow.google.com / https://labs.google/fx/tools/flow).
Key Capabilities:
  â”€ Character Consistency: Automatic @Character tagging and visual reference handling.
  â”€ Model Selection: Nano Banana, Imagen 3, Veo 3, Veo 3.1, Gemini Omni.
  â”€ Mode Selection: Image and Video generation.
  â”€ Aspect Ratio and Size Controls: 16:9, 9:16, 1:1, 4:3, 21:9.
  â”€ High-Fidelity Asset Capture: Native Playwright direct streaming & download intercept.
  â”€ Human-like typing & anti-detection stealth profiles.
"""

import asyncio
import base64
import random
import time
from pathlib import Path
from typing import Optional, Callable, List, TYPE_CHECKING

if TYPE_CHECKING:
    from models import Character

# â”€â”€â”€ Google Flow Selectors â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

FLOW_INPUT_SELECTORS = [
    'flow-rich-text-editor .ProseMirror',
    '.prompt-input .ProseMirror',
    'div.ProseMirror[contenteditable="true"]',
    '.ProseMirror[contenteditable="true"]',
    '.ProseMirror',
    'flow-prompt-box [contenteditable="true"]',
    'flow-base-prompt-box [contenteditable="true"]',
]

FLOW_GENERATE_BUTTON_SELECTORS = [
    'button[aria-label="Start generation"]',
    'button[aria-label*="Generate" i]',
    'button[aria-label*="Create" i]',
    'button:has-text("arrow_forward")',
    'button:has-text("Generate")',
    'button:has-text("Create")',
    '[data-testid="generate-button"]',
    '[data-testid="submit-button"]',
    'button[type="submit"]',
]

FLOW_MEDIA_SELECTORS = [
    'img[src*="flow-content.google"]',
    'img[src*="flow.google.com/asb/"]',
    'img[alt*="Tile displaying"]',
    'img.image',
    'video[src*="flow-content.google"]',
    'video[src*="blob:"]',
    'div[data-testid*="generation"] img',
    'div[data-testid*="generation"] video',
    'div[class*="output"] img',
    'div[class*="output"] video',
    'div[class*="result"] img',
    'div[class*="result"] video',
    'div[class*="media-card"] img',
    'div[class*="media-card"] video',
]
FLOW_MEDIA_SEL = ", ".join(FLOW_MEDIA_SELECTORS)

# â”€â”€â”€ Anti-detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--mute-audio",
    "--no-first-run",
    "--no-default-browser-check",
    "--lang=en-US,en",
    "--disable-features=IsolateOrigins,site-per-process",
    "--start-maximized",
    "--window-position=0,0",
]
IGNORE_ARGS = ["--enable-automation", "--enable-blink-features=IdleDetection"]

def _sanitize_profile_preferences(profile_dir: Path):
    """
    Sanitize profile Preferences so Chromium launches with a clean, normal UI:
    - Removes abnormal/off-screen window placement coordinates (which cause the browser window
      to overflow beyond the Windows desktop/work area and occlude the UI).
    - Ensures window_placement has maximized=True and top=0, left=0 so --start-maximized takes full effect.
    - Resets any saved per-host zoom levels (e.g. for flow.google.com) to normal 100% zoom.
    - Resets default_zoom_level to 0.
    """
    import json
    for pref_rel in ["Default/Preferences", "Preferences"]:
        pref_file = profile_dir / pref_rel
        if not pref_file.exists():
            continue
        try:
            data = json.loads(pref_file.read_text(encoding="utf-8"))
            changed = False

            if "partition" in data and isinstance(data["partition"], dict):
                if "per_host_zoom_levels" in data["partition"]:
                    data["partition"]["per_host_zoom_levels"] = {"x": {}}
                    changed = True

            if "default_zoom_level" in data:
                del data["default_zoom_level"]
                changed = True

            if "browser" in data and isinstance(data["browser"], dict):
                wp = data["browser"].get("window_placement")
                if isinstance(wp, dict):
                    wp["maximized"] = True
                    wp["top"] = 0
                    wp["left"] = 0
                    changed = True

            if changed:
                pref_file.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

def _get_stealth_script(cores: int, memory: int) -> str:
    return f'''
() => {{
    Object.defineProperty(navigator, 'webdriver',           {{get: () => undefined}});
    Object.defineProperty(navigator, 'languages',           {{get: () => ['en-US', 'en']}});
    Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {cores}}});
    Object.defineProperty(navigator, 'deviceMemory',        {{get: () => {memory}}});

    const orig = window.navigator.permissions.query;
    window.navigator.permissions.query = p =>
        p.name === 'notifications'
            ? Promise.resolve({{state: Notification.permission}})
            : orig(p);
    if (!window.chrome) window.chrome = {{runtime: {{}}}};
}}
'''

def _banner_script(color: str, name: str) -> str:
    """Colored banner stripe indicating active Google Flow account profile."""
    safe_name = name.replace("\\", "\\\\").replace("'", "\\'")[:30]
    text_color = "#000000"
    try:
        r2 = int(color[1:3], 16); g2 = int(color[3:5], 16); b2 = int(color[5:7], 16)
        text_color = "#ffffff" if (0.299*r2 + 0.587*g2 + 0.114*b2) < 128 else "#000000"
    except Exception:
        pass
    js = (
        "() => {"
        "  function ib() {"
        "    if (document.getElementById('__flow_banner__')) return;"
        "    const bar = document.createElement('div');"
        "    bar.id = '__flow_banner__';"
        "    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;height:4px;"
            "background:__COL__;z-index:2147483647;pointer-events:none;';"
        "    const tag = document.createElement('div');"
        "    tag.style.cssText = 'position:fixed;top:4px;right:0;z-index:2147483647;"
            "background:__COL__;color:__TXT__;font:bold 10px/1 monospace;"
            "padding:2px 8px 3px;border-radius:0 0 0 6px;pointer-events:none;';"
        "    tag.textContent = 'FLOW: __NM__';"
        "    const f = document.createDocumentFragment();"
        "    f.appendChild(bar); f.appendChild(tag);"
        "    (document.body||document.documentElement).appendChild(f);"
        "  }"
        "  document.body ? ib() : document.addEventListener('DOMContentLoaded',ib,{once:true});"
        "}"
    )
    return js.replace("__COL__", color).replace("__TXT__", text_color).replace("__NM__", safe_name)

# â”€â”€â”€ Response & Error Phrase Tables for Google Flow â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

FLAGGED_ACTIVITY_PHRASES = [
    "unusual activity",
    "browser extensions that modify the page",
    "we noticed some unusual activity",
    "temporarily disabled",
    "account suspended",
]

QUOTA_LIMIT_PHRASES = [
    "you've reached your generation limit",
    "generation limit reached",
    "daily limit reached",
    "quota exceeded",
    "out of generations",
    "too many generations",
    "upgrade your plan to generate more",
    "credits depleted",
    "insufficient credits",
]

RATE_LIMIT_PHRASES = [
    "too many requests",
    "please slow down",
    "temporarily unavailable",
    "try again in a few moments",
    "high traffic",
    "rate limit exceeded",
]

POLICY_PHRASES = [
    "violates our safety guidelines",
    "violates safety policy",
    "cannot generate this content",
    "content not permitted",
    "safety filter triggered",
    "flagged by our automated systems",
]

LOGIN_EXPIRED_PHRASES = [
    "sign in to continue",
    "please sign in",
    "session expired",
    "accounts.google.com/signin",
    "your google account session has expired",
]

GENERATION_ERROR_PHRASES = [
    "something went wrong",
    "generation failed",
    "failed to generate",
    "error occurred while processing",
    "try generating again",
]

# â”€â”€â”€ Exceptions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AutomationError(Exception):          pass
class RateLimitError(AutomationError):     pass
class QuotaLimitError(AutomationError):    pass
class PolicyError(AutomationError):        pass
class FlaggedAccountError(AutomationError): pass
class GenerationError(AutomationError):    pass
class LoginExpiredError(AutomationError):  pass
class LoginRequiredError(AutomationError): pass
class SkippedError(AutomationError):       pass
class NetworkError(AutomationError):       pass

# â”€â”€â”€ Single-Roundtrip Page State JS for Google Flow â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_FLOW_PAGE_STATE_JS = (
    "() => {"
    "  const spinSels = ["
    "    '[aria-busy=\"true\"]',"
    "    '.animate-spin',"
    "    '[class*=\"spinner\"]',"
    "    '[class*=\"loading\"]',"
    "    '[class*=\"generating\"]',"
    "    'progress',"
    "    '[role=\"progressbar\"]'"
    "  ];"
    "  const isGenerating = spinSels.some(s => !!document.querySelector(s));"
    ""
    f"  const mediaSels = `{FLOW_MEDIA_SEL}`;"
    "  const allMedia = [...document.querySelectorAll(mediaSels)];"
    "  const goodMedia = allMedia.filter(el => {"
    "    const src = el.src || el.currentSrc || '';"
    "    if (src.includes('googleusercontent.com/a/') || src.includes('gstatic.com') || src.includes('avatar')) return false;"
    "    if (el.tagName.toLowerCase() === 'img') {"
    "      return (src.includes('flow-content.google') || src.includes('flow.google.com/asb') || src.includes('blob:') || (el.naturalWidth >= 200 && el.naturalHeight >= 200));"
    "    } else if (el.tagName.toLowerCase() === 'video') {"
    "      return el.videoWidth >= 200 || el.duration > 0 || (el.src && el.src.length > 0);"
    "    }"
    "    return false;"
    "  });"
    ""
    "  const mediaSrcs = goodMedia.map(el => el.src || el.currentSrc || '').filter(Boolean);"
    "  const mediaItems = goodMedia.map((el, i) => ({"
    "    tag: el.tagName.toLowerCase(),"
    "    src: el.src || el.currentSrc || '',"
    "    w: el.naturalWidth || el.videoWidth || 0,"
    "    h: el.naturalHeight || el.videoHeight || 0,"
    "    idx: i"
    "  }));"
    ""
    "  const top = goodMedia[0];"
    "  const topMedia = top ? {"
    "    tag: top.tagName.toLowerCase(),"
    "    src: top.src || top.currentSrc || '',"
    "    w: top.naturalWidth || top.videoWidth || 0,"
    "    h: top.naturalHeight || top.videoHeight || 0,"
    "    idx: 0"
    "  } : null;"
    ""
    "  let inputEl = Array.from(document.querySelectorAll('flow-rich-text-editor .ProseMirror, .prompt-input .ProseMirror, div.ProseMirror[contenteditable=\"true\"], .ProseMirror[contenteditable=\"true\"], flow-prompt-box [contenteditable=\"true\"], flow-base-prompt-box [contenteditable=\"true\"], .ProseMirror')).find(el => {"
    "    let txt = ((el.getAttribute('placeholder') || '') + (el.getAttribute('aria-label') || '') + (el.getAttribute('id') || '') + (el.getAttribute('class') || '')).toLowerCase();"
    "    return el.isConnected && !txt.includes('search') && !txt.includes('find') && !txt.includes('filter') && !txt.includes('editable-text');"
    "  });"
    "  const inputReady = !!inputEl;"
    ""
    "  let alertText = '';"
    "  const errTileEl = document.querySelector('flow-error-tile, .error-tile, [class*=\"error-tile\"], .error-message, .error-subtitle');"
    "  if (errTileEl) {"
    "    alertText = (errTileEl.innerText || '').toLowerCase().trim();"
    "  }"
    "  if (!alertText) {"
    "    const toastEl = document.querySelector('[role=\"alert\"], .toast, [class*=\"error-banner\"], [class*=\"snackbar\"], flow-toast, flow-banner');"
    "    alertText = toastEl ? (toastEl.innerText || '').toLowerCase().trim() : '';"
    "  }"
    ""
    "  return {"
    "    isGenerating,"
    "    mediaCount: allMedia.length,"
    "    goodMediaCount: goodMedia.length,"
    "    mediaSrcs,"
    "    mediaItems,"
    "    topMedia,"
    "    inputReady,"
    "    alertText,"
    "  };"
    "}"
)


# â”€â”€â”€ Main Class â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class GoogleFlowAutomator:
    """
    Automates Google Flow (https://flow.google.com).
    One instance per active account session.
    """

    def __init__(
        self,
        profile_dir:   str,
        settings,                     # Settings dataclass
        log_callback:  Optional[Callable] = None,
        account_color: str = "#4285F4",
        account_name:  str = "Google Account",
    ):
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._cfg        = settings
        self.log         = log_callback or (lambda m, lvl="info": None)
        self._base_url   = getattr(settings, "flow_url", "https://flow.google.com").rstrip("/")
        self._acct_color = account_color
        self._acct_name  = account_name
        self._pw         = None
        self._ctx        = None
        self._page       = None
        self.running     = True

    # â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _s(self, attr: str, default=None):
        return getattr(self._cfg, attr, default)

    async def _sleep(self, attr: str, default: float = 1.0, scale: float = 1.0):
        await asyncio.sleep(self._s(attr, default) * scale)

    # â”€â”€ Lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_stable_fingerprint(self):
        # Generate stable profile-specific fingerprint details
        seed_val = hash(str(self.profile_dir))
        rnd = random.Random(seed_val)
        
        uas = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        ]
        resolutions = [
            (1920, 1080), (1366, 768), (1536, 864), (1440, 900), (2560, 1440)
        ]
        
        ua = rnd.choice(uas)
        res = rnd.choice(resolutions)
        cores = rnd.choice([4, 8, 12, 16])
        memory = rnd.choice([4, 8, 16, 32])
        return ua, res, cores, memory

    async def start(self):
        from playwright.async_api import async_playwright

        _sanitize_profile_preferences(self.profile_dir)

        ua, res, cores, memory = self._get_stable_fingerprint()

        # Add user-agent dynamically for this context to prevent static identical tracking across profiles
        custom_args = LAUNCH_ARGS.copy()
        custom_args.append(f"--user-agent={ua}")

        headless_mode = self._s("headless", False)
        launch_kwargs = {
            "headless": headless_mode,
            "args": custom_args,
            "ignore_default_args": IGNORE_ARGS,
            "is_mobile": False,
            "has_touch": False,
            "accept_downloads": True,
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
        if headless_mode:
            launch_kwargs["viewport"] = {"width": res[0], "height": res[1]}
            launch_kwargs["device_scale_factor"] = 1.0
        else:
            launch_kwargs["no_viewport"] = True

        self._pw  = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            str(self.profile_dir),
            **launch_kwargs,
        )
        await self._ctx.add_init_script(_get_stealth_script(cores, memory))
        await self._ctx.add_init_script(_banner_script(self._acct_color, self._acct_name))
        await self._ctx.add_init_script("""
(() => {
    const normalizeZoom = () => {
        if (document.body && !document.body.style.zoom) {
            document.body.style.zoom = '1.0';
        }
    };
    if (document.body) normalizeZoom();
    else document.addEventListener('DOMContentLoaded', normalizeZoom, {once: true});
})();
""")

        pages = self._ctx.pages
        self._page = pages[0] if pages else await self._ctx.new_page()
        self._page.on("console", lambda _: None)

        if headless_mode:
            try:
                await self._page.set_viewport_size({"width": res[0], "height": res[1]})
            except Exception:
                pass

        if not self._is_flow_page(self._page.url.lower()):
            try:
                await self._page.goto(self._base_url, wait_until="domcontentloaded", timeout=30_000)
                await self._sleep("page_load_settle", 2.0)
            except Exception as e:
                self.log(f"Navigation note: {e}", "warning")

        try:
            await self._page.evaluate("() => { if (document.body) document.body.style.zoom = '1.0'; }")
        except Exception:
            pass

        self.log(f"Google Flow Browser ready [{self._acct_name}]", "info")

    async def stop(self):
        self.running = False
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
        except Exception:
            pass
        try:
            if self._ctx:
                await self._ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._ctx = None
        self._pw = None

    def _is_flow_page(self, url: str) -> bool:
        return "flow.google" in url or "labs.google" in url

    # â”€â”€ Auth & Navigation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def check_login(self) -> bool:
        try:
            if not self._page or self._page.is_closed():
                return False
            url = self._page.url.lower()
            if any(w in url for w in ["accounts.google.com", "/signin", "/ServiceLogin"]):
                return False
            state = await self._get_state()
            return state.get("inputReady", False) or "flow.google.com" in url
        except Exception:
            return False

    async def goto_flow(self):
        try:
            if self._page and not self._page.is_closed():
                await self._page.goto(self._base_url, wait_until="domcontentloaded", timeout=30_000)
                await self._sleep("page_load_settle", 2.0)
        except Exception as e:
            self.log(f"Navigation error: {e}", "warning")

    async def health_check(self) -> bool:
        try:
            self.log("Health check â€” reloading Google Flowâ€¦", "warning")
            await self.goto_flow()
            if not await self.check_login():
                self.log("Health check: Google login required", "error")
                return False
            await self.new_project_or_session()
            self.log("Health check: Google Flow OK", "info")
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "error")
            return False

    async def new_project_or_session(self, force_home: bool = False):
        """Start or navigate to a fresh generation session/project.
        If force_home is True or if not on a project page, navigates to the Flow home page first
        and clicks '+ New project'.
        """
        if not self._page or self._page.is_closed():
            return

        if force_home or "project/" not in self._page.url:
            self.log("Navigating to Flow home page for fresh project...", "info")
            await self.goto_flow()
            await self._sleep("page_load_settle", 2.0)
        else:
            # If already on a project page and not forced home, check if prompt is ready
            if await self._wait_for_input(5):
                return

        for sel in [
            'button:has-text("New project")',
            'button:has-text("New Project")',
            'button[aria-label*="New project" i]',
            'button:has-text("add")',
            'button[aria-label="add New project"]',
            '[data-testid="create-project-button"]',
        ]:
            try:
                btn = await self._page.query_selector(sel)
                if btn:
                    await btn.click()
                    await self._sleep("new_chat_settle", 3.0)
                    break
            except Exception:
                continue
        await self._wait_for_input(15)

    # â”€â”€ Model, Aspect Ratio & Mode Selection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _configure_generation_settings(self, model_name: str, mode: str, aspect_ratio: str, image_count: str = "x1"):
        """
        Interacts with the Google Flow prompt bar controls to select the specified AI model,
        generation mode (image/video), aspect ratio, and image count.
        """
        if not self._page:
            return

        # Check settings trigger button (e.g. '🍌 Nano Banana 2 crop_16_9 x2')
        try:
            settings_trigger = await self._page.query_selector('button[aria-label="Settings trigger"], button[aria-label*="Settings trigger" i]')
            if settings_trigger:
                await settings_trigger.click()
                await asyncio.sleep(0.4)

                # Contextualize searches strictly to the opened overlay to avoid re-clicking the trigger button
                overlay = await self._page.query_selector('.cdk-overlay-pane')
                if not overlay:
                    await self._page.keyboard.press("Escape")
                    return

                # 0. Mode Selection
                if mode:
                    mode_text = "Video" if mode.lower() == "video" else "Image"
                    mode_btn = await overlay.query_selector(f'.mat-button-toggle-button:has-text("{mode_text}"), button:has-text("{mode_text}")')
                    if mode_btn:
                        await mode_btn.click()
                        await asyncio.sleep(0.2)

                # 1. Aspect Ratio Selection
                if aspect_ratio:
                    ar_opt = await overlay.query_selector(f'.mat-button-toggle-button:has-text("{aspect_ratio}"), button:has-text("{aspect_ratio}")')
                    if ar_opt:
                        await ar_opt.click()
                        await asyncio.sleep(0.2)

                # 2. Image Count Selection (x1, x2, x3, x4)
                if image_count:
                    # ensure 'x' prefix
                    clean_count = image_count if image_count.startswith("x") else f"x{image_count}"

                    # Some inputs might be stringified classes, ensure we extract actual value
                    if "COUNT_" in clean_count:
                        clean_count = clean_count.split("_")[-1].lower()
                        clean_count = f"x{clean_count}"

                    cnt_opt = await overlay.query_selector(f'.mat-button-toggle-button:has-text("{clean_count}"), button:has-text("{clean_count}"), [role="radio"]:has-text("{clean_count}")')
                    if cnt_opt:
                        await cnt_opt.click()
                        await asyncio.sleep(0.2)

                # 3. Model Selection
                if model_name:
                    model_btn = await overlay.query_selector('button[aria-label*="Select model" i]')
                    if model_btn:
                        curr_model = await model_btn.inner_text()
                        if model_name not in curr_model:
                            await model_btn.click()
                            await asyncio.sleep(0.4)

                            opt = await self._page.query_selector(f'.cdk-overlay-pane [role="menuitem"]:has-text("{model_name}"), .cdk-overlay-pane [role="option"]:has-text("{model_name}"), .cdk-overlay-pane button:has-text("{model_name}")')
                            if opt:
                                await opt.click()
                                await asyncio.sleep(0.3)
                            else:
                                await self._page.keyboard.press("Escape")
                                await asyncio.sleep(0.2)

                # Close menu by pressing Escape or clicking outside
                await self._page.keyboard.press("Escape")
                await asyncio.sleep(0.2)
        except Exception as ex:
            self.log(f"Model settings note: {ex}", "info")

    # ── Input & Character Tagging ─────────────────────────────────────────────

    async def _wait_for_input(self, timeout_s: float = 15) -> bool:
        deadline = time.monotonic() + timeout_s
        poll = self._s("input_poll_interval", 0.30)
        settle = self._s("input_confirm_settle", 0.18)
        while time.monotonic() < deadline and self.running:
            state = await self._get_state()
            if state.get("inputReady"):
                await asyncio.sleep(settle)
                return True
            await asyncio.sleep(poll)
        return False

    async def _get_input_element(self):
        if not self._page or self._page.is_closed():
            return None

        # Look for the prompt editor, specifically targeting flow prompt elements and rejecting search/title inputs
        for sel in FLOW_INPUT_SELECTORS:
            try:
                elements = await self._page.query_selector_all(sel)
                for el in elements:
                    if not el:
                        continue

                    # Ensure element is not a search bar or project title input via attributes, classes, and IDs
                    aria = (await el.get_attribute("aria-label") or "").lower()
                    placeholder = (await el.get_attribute("placeholder") or "").lower()
                    type_attr = (await el.get_attribute("type") or "").lower()
                    name_attr = (await el.get_attribute("name") or "").lower()
                    id_attr = (await el.get_attribute("id") or "").lower()
                    class_attr = (await el.get_attribute("class") or "").lower()

                    is_search = any("search" in x or "find" in x or "query" in x or "filter" in x or "editable-text" in x for x in [aria, placeholder, type_attr, name_attr, id_attr, class_attr])
                    if is_search:
                        continue

                    if await el.is_visible():
                        return el
            except Exception:
                pass
        return None

    async def _recover_prompt_focus(self):
        """Dismiss active card selections, overlays, and refocus the prompt input in the current project."""
        if not self._page or self._page.is_closed():
            return
        try:
            # 1. Press Escape twice to clear node selection and close menus
            await self._page.keyboard.press("Escape")
            await asyncio.sleep(0.15)
            await self._page.keyboard.press("Escape")
            await asyncio.sleep(0.15)

            # 2. Click neutral canvas area to deselect any selected card
            for sel in ['flow-canvas', '.flow-canvas', 'main', 'body']:
                canvas = await self._page.query_selector(sel)
                if canvas:
                    try:
                        box = await canvas.bounding_box()
                        if box:
                            await self._page.mouse.click(box["x"] + 100, box["y"] + 100)
                            await asyncio.sleep(0.2)
                            break
                    except Exception:
                        pass

            # 3. Focus/click the prompt container if found
            for sel in FLOW_INPUT_SELECTORS + ['flow-prompt-box', 'flow-rich-text-editor']:
                el = await self._page.query_selector(sel)
                if el and await el.is_visible():
                    try:
                        await el.click()
                        await asyncio.sleep(0.15)
                        break
                    except Exception:
                        pass
        except Exception:
            pass

    async def _type_prompt(self, text: str):
        ready = await self._wait_for_input(10)
        if not ready:
            await self._recover_prompt_focus()
            ready = await self._wait_for_input(10)
            if not ready:
                raise AutomationError("Google Flow prompt input not found")

        el = await self._get_input_element()
        if el:
            try:
                box = await el.bounding_box()
                if box:
                    x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
                    y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
                    steps = self._s("mouse_move_steps", 8)
                    await self._page.mouse.move(x, y, steps=steps)
                    await asyncio.sleep(random.uniform(0.05, 0.15))
                    await el.click()
                    await asyncio.sleep(random.uniform(0.08, 0.18))
            except Exception:
                pass

        _ks = max(0.03, self._s("input_confirm_settle", 0.18) * 0.35)

        # Ensure we are focused on the element before typing
        el = await self._get_input_element()
        if el:
            await el.focus()

        await self._page.keyboard.press("Control+a")
        await asyncio.sleep(_ks)
        await self._page.keyboard.press("Delete")
        await asyncio.sleep(_ks * 1.5)

        wpm = self._s("type_wpm", 85)
        variance = self._s("type_variance", 0.35)
        burst_ch = self._s("type_burst_chance", 0.15)
        pause_ch = self._s("type_pause_chance", 0.10)
        base_delay = 60.0 / (wpm * 5)

        words = text.split(" ")
        i = 0
        in_burst = 0

        while i < len(words) and self.running:
            word = words[i]

            if in_burst <= 0 and random.random() < burst_ch:
                in_burst = random.randint(3, 6)

            if in_burst > 0:
                char_delay = base_delay * random.uniform(0.3, 0.5)
                in_burst -= 1
            else:
                v = variance * random.uniform(-1, 1)
                char_delay = base_delay * (1.0 + v)
                char_delay = max(0.01, char_delay)

            # Detect if typing '@' stole focus from the ProseMirror
            if word.startswith("@"):
                # Type the tag all at once or fast
                await self._page.keyboard.type(word)
                await asyncio.sleep(0.4)

                # Check for the overlay options from the character mention popup
                try:
                    # Google flow uses CDK overlay for both mentions and menus.
                    char_opt = await self._page.query_selector('.cdk-overlay-pane [role="option"], .character-suggestion')
                    if char_opt:
                        await self._page.keyboard.press("Enter")
                        await asyncio.sleep(0.2)
                except Exception:
                    pass

                # RE-FOCUS check: The `@` might have popped a search bar that stole focus.
                # If activeElement is an input field and not contenteditable, hit Escape to close it and refocus editor.
                try:
                    is_bad_focus = await self._page.evaluate("""() => {
                        let a = document.activeElement;
                        return a && a.tagName === 'INPUT' && !a.isContentEditable;
                    }""")
                    if is_bad_focus:
                        await self._page.keyboard.press("Escape")
                        await asyncio.sleep(0.2)
                        el_refocus = await self._get_input_element()
                        if el_refocus:
                            await el_refocus.click()
                except Exception:
                    pass

            else:
                # Normal word typing
                sep = " " if i < len(words) - 1 else ""
                await self._page.keyboard.type(word + sep, delay=int(char_delay * 1000))

            if word.endswith((",", ";", "â€”")) and random.random() < pause_ch:
                await asyncio.sleep(random.uniform(0.18, 0.55))
            elif word.endswith((".", "!", "?")) and random.random() < pause_ch * 1.5:
                await asyncio.sleep(random.uniform(0.25, 0.70))
            else:
                await asyncio.sleep(char_delay * random.uniform(0.2, 0.6))

            i += 1

        # Direct DOM input fallback verification
        try:
            el = await self._get_input_element()
            if el:
                inner = await el.inner_text()
                if len(inner.strip()) < max(3, int(len(text.strip()) * 0.85)):
                    await el.click()
                    await self._page.keyboard.press("Control+a")
                    await self._page.keyboard.press("Delete")
                    await self._page.evaluate(
                        "(t) => {"
                        "  let el = Array.from(document.querySelectorAll('flow-rich-text-editor .ProseMirror, .prompt-input .ProseMirror, div.ProseMirror[contenteditable=\"true\"], .ProseMirror[contenteditable=\"true\"], flow-prompt-box [contenteditable=\"true\"], flow-base-prompt-box [contenteditable=\"true\"], .ProseMirror')).find(e => {"
                        "    let aria = (e.getAttribute('aria-label') || '').toLowerCase();"
                        "    let ph = (e.getAttribute('placeholder') || '').toLowerCase();"
                        "    let nameAttr = (e.getAttribute('name') || '').toLowerCase();"
                        "    let idAttr = (e.getAttribute('id') || '').toLowerCase();"
                        "    let clsAttr = (e.getAttribute('class') || '').toLowerCase();"
                        "    let desc = aria + ph + nameAttr + idAttr + clsAttr;"
                        "    let isSearch = desc.includes('search') || desc.includes('find') || desc.includes('query') || desc.includes('filter') || desc.includes('editable-text');"
                        "    let isContentEditable = e.getAttribute('contenteditable') === 'true' || e.isContentEditable;"
                        "    return e.isConnected && !isSearch && isContentEditable;"
                        "  });"
                        "  if (el) { el.focus(); document.execCommand('insertText', false, t); }"
                        "}", text
                    )
        except Exception:
            pass

    async def _submit_generation(self):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and self.running:
            for sel in FLOW_GENERATE_BUTTON_SELECTORS:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and not await btn.get_attribute("disabled"):
                        await asyncio.sleep(random.uniform(0.1, 0.3))
                        await btn.click()
                        return
                except Exception:
                    continue
            await asyncio.sleep(self._s("send_poll_interval", 0.30))

        # Enter key trigger
        el = await self._get_input_element()
        if el:
            await el.press("Enter")
        else:
            raise AutomationError("Google Flow Generate button not found")

    # â”€â”€ State & Classifier â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _get_state(self) -> dict:
        try:
            if not self._page or self._page.is_closed():
                return {"isGenerating": False, "mediaCount": 0, "goodMediaCount": 0,
                        "topMedia": None, "inputReady": False, "alertText": ""}
            return await self._page.evaluate(_FLOW_PAGE_STATE_JS)
        except Exception:
            return {"isGenerating": False, "mediaCount": 0, "goodMediaCount": 0,
                    "topMedia": None, "inputReady": False, "alertText": ""}

    def _classify_alert_text(self, text: str):
        t = text.lower()
        if any(p in t for p in FLAGGED_ACTIVITY_PHRASES):
            return "FLAGGED_ACTIVITY", FlaggedAccountError(f"Account flagged for unusual activity: {text[:80]!r}")
        if any(p in t for p in QUOTA_LIMIT_PHRASES):
            return "QUOTA_LIMIT", QuotaLimitError("Google Flow generation quota limit reached")
        if any(p in t for p in RATE_LIMIT_PHRASES):
            return "RATE_LIMIT", RateLimitError("Google Flow rate limited")
        if any(p in t for p in POLICY_PHRASES):
            return "POLICY", PolicyError(f"Google Flow safety policy: {text[:80]!r}")
        if any(p in t for p in LOGIN_EXPIRED_PHRASES):
            return "LOGIN_EXPIRED", LoginExpiredError("Google session expired")
        if any(p in t for p in GENERATION_ERROR_PHRASES):
            return "GEN_ERROR", GenerationError(f"Flow generation error: {text[:80]!r}")
        return "OK", None

    # â”€â”€ Download & Image/Video Processing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _download_media(self, media_info: dict, save_path: Path) -> bool:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        min_bytes = self._s("min_image_bytes", 15_000)
        url = media_info.get("src", "")

        # 1. Direct binary fetch via Playwright Request context (handles authenticated media streams)
        if self._ctx and url.startswith("http"):
            try:
                response = await self._ctx.request.get(url, timeout=30_000)
                if response.ok:
                    body = await response.body()
                    if len(body) >= min_bytes:
                        save_path.write_bytes(body)
                        return True
            except Exception as e:
                self.log(f"Direct stream download note: {e}", "info")

        # 2. Native Download Button check
        try:
            dl_btn = await self._page.query_selector('button[aria-label*="download" i], [data-testid*="download" i], a[download]')
            if dl_btn:
                async with self._page.expect_download(timeout=30_000) as dl_info:
                    await dl_btn.click()
                download = await dl_info.value
                await download.save_as(str(save_path))
                if save_path.exists() and save_path.stat().st_size >= min_bytes:
                    return True
                if save_path.exists():
                    save_path.unlink(missing_ok=True)
        except Exception:
            pass

        # 3. In-page Fetch ArrayBuffer fallback
        if url.startswith("http") or url.startswith("blob:"):
            try:
                b64 = await self._page.evaluate("""
                    async (u) => {
                        const r = await fetch(u, {credentials:'include'});
                        if (!r.ok) throw new Error('HTTP ' + r.status);
                        const buf = await r.arrayBuffer();
                        const u8 = new Uint8Array(buf);
                        let bin = ''; const C = 8192;
                        for (let i = 0; i < u8.length; i += C)
                            bin += String.fromCharCode(...u8.subarray(i, i+C));
                        return btoa(bin);
                    }
                """, url)
                if b64:
                    data = base64.b64decode(b64)
                    if len(data) >= min_bytes:
                        save_path.write_bytes(data)
                        return True
            except Exception:
                pass

        return False

    # â”€â”€ Wait Loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _wait_for_generation(self, initial_count: int, known_srcs: set = None) -> list:
        """Wait for a genuinely new media element(s) not present before generation.

        Args:
            initial_count: total allMedia count before the prompt was submitted.
            known_srcs:    set of good-media src URLs on the page before
                           generation started. Prevents stale images from
                           earlier prompts in the same session being returned.
        """
        stable_time = self._s("image_stable_time", 4.0)
        timeout = self._s("generation_timeout", 420.0)
        p_gen = self._s("poll_generating", 0.8)
        p_post = self._s("poll_post_stop", 0.5)
        p_stable = self._s("poll_stable", 0.8)
        p_idle = self._s("poll_idle", 1.0)

        if known_srcs is None:
            known_srcs = set()

        start = time.monotonic()
        seen_generating = False
        resubmit_attempted = False
        stopped_at = None
        stable_since = None
        last_sig = None

        while self.running:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise TimeoutError(f"Google Flow generation timed out after {int(timeout)}s")

            # Check if generation never even started after 20s; attempt resubmit once
            if not seen_generating and elapsed > 20.0 and not resubmit_attempted:
                resubmit_attempted = True
                self.log("Generation did not start after 20s, re-checking prompt box and re-submitting...", "debug")
                try:
                    await self._page.keyboard.press("Enter")
                    await self._submit_generation()
                except Exception:
                    pass

            # If generation never started and no media changed after 75s, fail fast so worker can retry
            if not seen_generating and elapsed > 75.0:
                raise GenerationError("Generation did not start within 75s (no generating indicator)")

            state = await self._get_state()
            generating = state["isGenerating"]
            top_media = state["topMedia"]
            alert_text = state["alertText"]
            media_items: list = state.get("mediaItems") or []

            # Error banner classification
            if alert_text:
                outcome, exc = self._classify_alert_text(alert_text)
                if exc:
                    self.log(f"Alert: {outcome} - {alert_text[:60]}", "warning")
                    raise exc

            # Active generation
            if generating:
                seen_generating = True
                stopped_at = None
                await asyncio.sleep(p_gen)
                continue

            if seen_generating and stopped_at is None:
                stopped_at = time.monotonic()
                await asyncio.sleep(p_post)
                continue

            # Identify genuinely new media items
            if known_srcs:
                candidates = [m for m in media_items if m.get("src") and m.get("src") not in known_srcs]
            else:
                candidates = media_items if media_items else ([top_media] if top_media else [])

            if not candidates or not candidates[0].get("src"):
                await asyncio.sleep(p_post if stopped_at else p_idle)
                continue

            # Check stability of the candidates
            src = candidates[-1]["src"]
            sig = f"{len(candidates)}|{src}|{candidates[-1].get('w', 0)}x{candidates[-1].get('h', 0)}"
            now = time.monotonic()

            if sig != last_sig:
                last_sig = sig
                stable_since = now
                await asyncio.sleep(p_stable)
                continue

            if (now - stable_since) >= stable_time:
                self.log(f"New media stable ({len(candidates)} items): ...{src[-40:]}", "info")
                return candidates

            await asyncio.sleep(p_stable)

        raise SkippedError("Worker stopped")

    # â”€â”€ Main Run Prompt â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def run_prompt(
        self,
        prompt_text: str,
        save_path: Path,
        character: Optional["Character"] = None,
        model_name: str = "Nano Banana",
        mode: str = "image",
        aspect_ratio: str = "16:9",
        image_count: str = "x1",
        do_new_session: bool = False
    ) -> List[str]:
        if do_new_session:
            await self.new_project_or_session(force_home=True)
        else:
            if not await self._wait_for_input(5):
                # Try recovering prompt focus (clear canvas selection, click prompt box)
                await self._recover_prompt_focus()
                if not await self._wait_for_input(10):
                    # Reload project page to reset canvas state without abandoning project
                    self.log("Prompt input not focused; reloading project canvas...", "warning")
                    try:
                        await self._page.reload()
                        await asyncio.sleep(3)
                        await self._recover_prompt_focus()
                    except Exception:
                        pass
                    if not await self._wait_for_input(15):
                        raise AutomationError("Google Flow input not ready")

        if any(w in self._page.url.lower() for w in ["accounts.google.com/signin", "/ServiceLogin"]):
            raise LoginExpiredError("Google session expired")

        # Configure settings explicitly here (model, aspect ratio, mode, batch count)
        await self._configure_generation_settings(model_name, mode, aspect_ratio, image_count)

        state = await self._get_state()
        initial_count = state["mediaCount"]
        known_srcs = set(state.get("mediaSrcs") or [])

        await self._type_prompt(prompt_text)
        await self._submit_generation()
        self.log(f"Sent: {prompt_text[:65]}…", "info")

        # Quick check for immediate rejection (e.g. Unusual Activity or safety banner)
        await asyncio.sleep(1.0)
        early_state = await self._get_state()
        if early_state.get("alertText"):
            outcome, exc = self._classify_alert_text(early_state["alertText"])
            if exc:
                self.log(f"Immediate Alert: {outcome} — {early_state['alertText'][:60]}", "warning")
                raise exc

        media_infos = await self._wait_for_generation(initial_count, known_srcs)
        if not media_infos:
            raise AutomationError("No generated media found")

        saved_paths = []
        for idx, media_info in enumerate(media_infos):
            if idx == 0:
                target_path = save_path
            else:
                # Add suffix: filename_2.png, filename_3.png, etc.
                target_path = save_path.parent / f"{save_path.stem}_{idx + 1}{save_path.suffix}"

            ok = await self._download_media(media_info, target_path)
            if ok:
                saved_paths.append(str(target_path))

        if not saved_paths:
            raise AutomationError("Google Flow media download failed for all images")

        return saved_paths

    # â”€â”€ Diagnostic Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def test_login(self) -> bool:
        result = await self.check_login()
        self.log(f"[TEST] Google Flow Login: {'âœ…' if result else 'âŒ'}", "info")
        return result

    async def test_screenshot(self, save_path: Path) -> bool:
        try:
            await self._page.screenshot(path=str(save_path), full_page=False)
            self.log(f"[TEST] Screenshot â†’ {save_path}", "success")
            return True
        except Exception as e:
            self.log(f"[TEST] Screenshot failed: {e}", "error")
            return False
