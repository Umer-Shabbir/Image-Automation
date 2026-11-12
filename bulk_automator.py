# bulk_automator.py
"""
Bulk Media Generator Automation Engine.
Automates the Gemini Canvas Bulk Media App (https://gemini.google.com/share/79e5de5150e6).

Key Capabilities:
  ─ Disclaimer auto-acknowledgment ("Continue" button).
  ─ Dynamic iframe discovery and synchronization.
  ─ Aspect ratio and consistency controls.
  ─ Bulk prompt submission with 1-to-1 prompt-to-image tracking.
  ─ Lossless, direct Base64 stream decoding and file persistence.
  ─ Per-project isolated saving to prevent cross-contamination.
"""

import asyncio
import base64
import random
import time
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from models import Character, Job, Settings

from automator import (
    LAUNCH_ARGS,
    IGNORE_ARGS,
    _sanitize_profile_preferences,
    _get_stealth_script,
    AutomationError,
    QuotaLimitError,
    RateLimitError,
    PolicyError,
    FlaggedAccountError,
    LoginExpiredError,
)


def _bulk_banner_script(color: str, name: str) -> str:
    """Banner stripe indicating active account profile on Bulk App."""
    safe_name = name.replace("\\", "\\\\").replace("'", "\\'")[:30]
    text_color = "#000000"
    try:
        r2 = int(color[1:3], 16); g2 = int(color[3:5], 16); b2 = int(color[5:7], 16)
        text_color = "#ffffff" if (0.299 * r2 + 0.587 * g2 + 0.114 * b2) < 128 else "#000000"
    except Exception:
        pass
    js = (
        "() => {"
        "  function ib() {"
        "    if (document.getElementById('__bulk_banner__')) return;"
        "    const bar = document.createElement('div');"
        "    bar.id = '__bulk_banner__';"
        "    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;height:4px;"
            "background:__COL__;z-index:2147483647;pointer-events:none;';"
        "    const tag = document.createElement('div');"
        "    tag.style.cssText = 'position:fixed;top:4px;right:0;z-index:2147483647;"
            "background:__COL__;color:__TXT__;font:bold 10px/1 monospace;"
            "padding:2px 8px 3px;border-radius:0 0 0 6px;pointer-events:none;';"
        "    tag.textContent = 'BULK APP: __NM__';"
        "    const f = document.createDocumentFragment();"
        "    f.appendChild(bar); f.appendChild(tag);"
        "    (document.body||document.documentElement).appendChild(f);"
        "  }"
        "  document.body ? ib() : document.addEventListener('DOMContentLoaded',ib,{once:true});"
        "}"
    )
    return js.replace("__COL__", color).replace("__TXT__", text_color).replace("__NM__", safe_name)


class BulkAppAutomator:
    """
    Automates the Bulk Media Generator app hosted inside Gemini Canvas.
    """

    def __init__(
        self,
        profile_dir: str,
        settings,  # Settings dataclass
        log_callback: Optional[Callable] = None,
        account_color: str = "#4285F4",
        account_name: str = "Google Account",
    ):
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._cfg = settings
        self.log = log_callback or (lambda m, lvl="info": None)
        self._base_url = getattr(settings, "bulk_app_url", "https://gemini.google.com/share/79e5de5150e6").strip()
        if not self._base_url:
            self._base_url = "https://gemini.google.com/share/79e5de5150e6"
        self._acct_color = account_color
        self._acct_name = account_name
        self._pw = None
        self._ctx = None
        self._page = None
        self.running = True

    def _s(self, attr: str, default=None):
        return getattr(self._cfg, attr, default)

    def _get_stable_fingerprint(self):
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
        memory = rnd.choice([8, 16, 32])
        return ua, res, cores, memory

    async def start(self):
        from playwright.async_api import async_playwright

        _sanitize_profile_preferences(self.profile_dir)
        ua, res, cores, memory = self._get_stable_fingerprint()

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

        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            str(self.profile_dir),
            **launch_kwargs,
        )
        await self._ctx.add_init_script(_get_stealth_script(cores, memory))
        await self._ctx.add_init_script(_bulk_banner_script(self._acct_color, self._acct_name))

        pages = self._ctx.pages
        self._page = pages[0] if pages else await self._ctx.new_page()

        if headless_mode:
            try:
                await self._page.set_viewport_size({"width": res[0], "height": res[1]})
            except Exception:
                pass

        try:
            await self._page.goto(self._base_url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(2.0)
        except Exception as e:
            self.log(f"Navigation note: {e}", "warning")

        await self.ensure_app_ready()
        self.log(f"Bulk App Browser ready [{self._acct_name}]", "info")

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

    async def check_login(self) -> bool:
        try:
            if not self._page or self._page.is_closed():
                return False
            url = self._page.url.lower()
            if any(w in url for w in ["accounts.google.com", "/signin", "/servicelogin"]):
                return False
            
            # Check for unauthenticated 'Sign in' button on gemini page
            signin_btn = await self._page.query_selector('a:has-text("Sign in"), button:has-text("Sign in"), a[href*="accounts.google.com"]')
            if signin_btn and await signin_btn.is_visible():
                return False

            # Check if app iframe or continue button is visible
            frame = await self._get_app_frame()
            if frame is not None:
                return True
            continue_btn = await self._page.query_selector('button:has-text("Continue"), .confirm-button')
            return continue_btn is not None or "gemini.google.com" in url
        except Exception:
            return False

    async def _handle_disclaimer(self):
        """Clicks 'Continue' on the shared Gemini app disclaimer screen if present."""
        if not self._page or self._page.is_closed():
            return
        try:
            for _ in range(3):
                btn = await self._page.query_selector('button:has-text("Continue"), .confirm-button')
                if btn and await btn.is_visible():
                    self.log("Acknowledging app disclaimer screen...", "info")
                    await btn.click()
                    await asyncio.sleep(3.0)
                    break
                await asyncio.sleep(1.0)
        except Exception:
            pass

    async def _get_app_frame(self):
        """Finds the iframe containing the Bulk Media Generator app."""
        if not self._page or self._page.is_closed():
            return None
        for f in self._page.frames:
            try:
                has_input = await f.query_selector('#prompt-input')
                if has_input:
                    return f
            except Exception:
                pass
        return None

    async def ensure_app_ready(self, timeout_s: float = 30.0) -> bool:
        """Ensures the app iframe is loaded, disclaimer dismissed, and prompt input available."""
        start = time.monotonic()
        while time.monotonic() - start < timeout_s and self.running:
            await self._handle_disclaimer()
            frame = await self._get_app_frame()
            if frame:
                try:
                    inp = await frame.query_selector('#prompt-input')
                    btn = await frame.query_selector('#generate-btn')
                    if inp and btn:
                        return True
                except Exception:
                    pass
            await asyncio.sleep(1.5)
        return False

    async def run_bulk_generation(
        self,
        batch_jobs: List["Job"],
        aspect_ratio: str = "16:9",
        character_desc: str = "",
        style_desc: str = "",
    ) -> Dict[str, Dict[str, Any]]:
        """
        Executes bulk image generation for a batch of jobs in the Bulk App.
        Ensures strict 1-to-1 prompt-to-image mapping by index:
          batch_jobs[k] <--> line[k] <--> img-card-k <--> generatedImages[k].
        Saves each generated image directly to the corresponding job's save path.
        """
        if not batch_jobs:
            return {}

        ready = await self.ensure_app_ready(20.0)
        if not ready:
            raise AutomationError("Bulk App input frame not accessible")

        frame = await self._get_app_frame()
        if not frame:
            raise AutomationError("Bulk App iframe not found")

        # 1. Clean prompts: strip internal newlines to guarantee 1 prompt per line
        cleaned_prompts = []
        for j in batch_jobs:
            p_text = (j.prompt_text or "").replace("\r", " ").replace("\n", " ").strip()
            # Collapse multiple spaces
            while "  " in p_text:
                p_text = p_text.replace("  ", " ")
            cleaned_prompts.append(p_text or "Creative artwork")

        # Prompts are separated by an empty line: 1 \n\n 2 \n\n 3
        bulk_text = "\n\n".join(cleaned_prompts)
        total_prompts = len(cleaned_prompts)

        self.log(f"Submitting {total_prompts} prompts in bulk to Bulk Media Generator...", "info")

        # 2. Configure Aspect Ratio on <select id="aspect-ratio">
        if aspect_ratio:
            try:
                clean_ar = aspect_ratio.strip()
                await frame.select_option('#aspect-ratio', value=clean_ar)
                await asyncio.sleep(0.3)
            except Exception as e:
                self.log(f"Aspect ratio setting note: {e}", "info")

        # 3. Configure Character Consistency text if provided
        if character_desc:
            try:
                char_cb = await frame.query_selector('#char-consistency')
                if char_cb and not await char_cb.is_checked():
                    await char_cb.check()
                await frame.fill('#char-desc', character_desc)
            except Exception:
                pass
        else:
            try:
                char_cb = await frame.query_selector('#char-consistency')
                if char_cb and await char_cb.is_checked():
                    await char_cb.uncheck()
                await frame.fill('#char-desc', '')
            except Exception:
                pass

        # 4. Configure Style Consistency text if provided
        if style_desc:
            try:
                style_cb = await frame.query_selector('#style-consistency')
                if style_cb and not await style_cb.is_checked():
                    await style_cb.check()
                await frame.fill('#style-desc', style_desc)
            except Exception:
                pass
        else:
            try:
                style_cb = await frame.query_selector('#style-consistency')
                if style_cb and await style_cb.is_checked():
                    await style_cb.uncheck()
                await frame.fill('#style-desc', '')
            except Exception:
                pass

        # 5. Clear and populate #prompt-input and dispatch input event
        await frame.fill('#prompt-input', '')
        await asyncio.sleep(0.2)
        await frame.fill('#prompt-input', bulk_text)
        await asyncio.sleep(0.5)
        await frame.evaluate("""() => {
            const el = document.getElementById('prompt-input');
            if (el) {
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }""")
        await asyncio.sleep(0.5)

        # 6. Click GENERATE MEDIA button
        gen_btn = await frame.query_selector('#generate-btn')
        if not gen_btn:
            raise AutomationError("Generate button #generate-btn not found in app")

        await gen_btn.click()
        self.log("Bulk generation triggered. Awaiting concurrent results...", "info")
        await asyncio.sleep(2.0)

        # 7. Poll until generation completes or timeout
        timeout = max(180.0, total_prompts * 45.0)
        start_t = time.monotonic()
        poll_interval = 2.0

        while self.running:
            elapsed = time.monotonic() - start_t
            if elapsed > timeout:
                raise TimeoutError(f"Bulk generation timed out after {int(timeout)}s")

            status_info = await frame.evaluate("""() => {
                const progText = document.getElementById('progress-text')?.innerText || '';
                const progBar = document.getElementById('progress-bar');
                const progWidth = progBar ? progBar.style.width : '';
                const isGen = (typeof isGenerating !== 'undefined') ? isGenerating : false;
                const genCount = (typeof generatedImages !== 'undefined') ? generatedImages.length : 0;
                
                // Count completed cards vs failed cards
                const cards = Array.from(document.querySelectorAll('.image-card'));
                let completedCards = 0;
                let failedCards = 0;
                cards.forEach(c => {
                    if (c.querySelector('img')) completedCards++;
                    if (c.innerText.includes('Generation Failed')) failedCards++;
                });

                return {
                    progText,
                    progWidth,
                    isGen,
                    genCount,
                    totalCards: cards.length,
                    completedCards,
                    failedCards
                };
            }""")

            completed_or_failed = status_info["completedCards"] + status_info["failedCards"]
            self.log(
                f"Bulk progress: {status_info['completedCards']}/{total_prompts} generated "
                f"({status_info['failedCards']} failed) — {status_info['progText']}",
                "debug"
            )

            # Check if all prompts have resolved
            if not status_info["isGen"] and (
                completed_or_failed >= total_prompts
                or status_info["progWidth"] == "100%"
                or "Complete" in status_info["progText"]
                or "Stopped" in status_info["progText"]
            ):
                await asyncio.sleep(1.0)
                break

            await asyncio.sleep(poll_interval)

        # Auto-retry any failed cards directly in the app before giving up
        if status_info.get("failedCards", 0) > 0:
            self.log(f"Detected {status_info['failedCards']} failed cards. Triggering in-app auto-retry...", "warning")
            try:
                retried = await frame.evaluate("""async () => {
                    const cards = Array.from(document.querySelectorAll('.image-card'));
                    const failedIndices = [];
                    cards.forEach((c, idx) => {
                        if (c.innerText.includes('Generation Failed') || !c.querySelector('img')) {
                            failedIndices.push(idx);
                        }
                    });
                    if (failedIndices.length === 0) return 0;
                    const aspect = document.getElementById('aspect-ratio')?.value || '16:9';
                    for (const idx of failedIndices) {
                        const p = (typeof activePrompts !== 'undefined' && activePrompts[idx]) || (typeof prompts !== 'undefined' && prompts[idx]);
                        if (p && typeof generateImage === 'function') {
                            await generateImage(p, aspect, idx, cards.length, true);
                            await new Promise(r => setTimeout(r, 1500));
                        }
                    }
                    return failedIndices.length;
                }""")
                if retried:
                    await asyncio.sleep(3.0)
            except Exception as e:
                self.log(f"In-app auto-retry note: {e}", "debug")

        # 8. Extract all images mapped 1-to-1 to their prompt index
        image_data_map = await frame.evaluate("""() => {
            const out = {};
            // 1. From generatedImages array
            if (typeof generatedImages !== 'undefined' && Array.isArray(generatedImages)) {
                generatedImages.forEach(img => {
                    if (img && typeof img.index !== 'undefined' && img.url) {
                        out[img.index] = {
                            url: img.url,
                            prompt: img.prompt || '',
                            status: 'success'
                        };
                    }
                });
            }
            // 2. Fallback to DOM inspection per card
            const cards = Array.from(document.querySelectorAll('.image-card'));
            cards.forEach((c, idx) => {
                if (!out[idx]) {
                    const img = c.querySelector('img');
                    if (img && img.src && img.src.startsWith('data:image')) {
                        out[idx] = {
                            url: img.src,
                            prompt: img.alt || '',
                            status: 'success'
                        };
                    } else if (c.innerText.includes('Generation Failed')) {
                        const errP = c.querySelector('.break-words') || c.querySelector('p:nth-child(3)');
                        out[idx] = {
                            url: '',
                            prompt: '',
                            status: 'failed',
                            error: errP ? errP.innerText : 'Generation failed'
                        };
                    }
                }
            });
            return out;
        }""")

        # 9. Save each image to its respective job save path
        from worker import compute_job_save_path

        results: Dict[str, Dict[str, Any]] = {}
        min_bytes = self._s("min_image_bytes", 15_000)

        for idx, job in enumerate(batch_jobs):
            idx_str = str(idx)
            info = image_data_map.get(idx_str) or image_data_map.get(idx)
            target_path = compute_job_save_path(job, self._cfg, "image")
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if info and info.get("status") == "success" and info.get("url"):
                data_url = info["url"]
                try:
                    # Parse Base64 data URI
                    if "," in data_url:
                        b64_str = data_url.split(",", 1)[1]
                    else:
                        b64_str = data_url
                    img_bytes = base64.b64decode(b64_str)

                    if len(img_bytes) >= min_bytes:
                        target_path.write_bytes(img_bytes)
                        results[job.id] = {
                            "success": True,
                            "file_path": str(target_path),
                            "error": ""
                        }
                        try:
                            self.log(f"[SAVED] #{job.global_index} -> {target_path.name} ({len(img_bytes):,} bytes)", "success")
                        except Exception:
                            pass
                    else:
                        results[job.id] = {
                            "success": False,
                            "file_path": "",
                            "error": f"Image file too small ({len(img_bytes)} bytes)"
                        }
                except Exception as e:
                    results[job.id] = {
                        "success": False,
                        "file_path": "",
                        "error": f"Base64 decode error: {e}"
                    }
            else:
                err = info.get("error") if info else "No image produced"
                results[job.id] = {
                    "success": False,
                    "file_path": "",
                    "error": err
                }
                try:
                    self.log(f"[FAILED] #{job.global_index} failed: {err}", "warning")
                except Exception:
                    pass

        return results

    async def run_prompt(
        self,
        prompt_text: str,
        save_path: Path,
        aspect_ratio: str = "16:9",
        character_desc: str = "",
        style_desc: str = "",
        **kwargs
    ) -> List[str]:
        from models import Job
        save_path_p = Path(save_path)
        proj_folder = str(save_path_p.parent.parent if save_path_p.parent.name in ["images", "thumbnails", "videos"] else save_path_p.parent)
        mock_job = Job(prompt_text=prompt_text, file_path=str(save_path_p), project_folder=proj_folder)
        results = await self.run_bulk_generation([mock_job], aspect_ratio=aspect_ratio, character_desc=character_desc, style_desc=style_desc)
        res = results.get(mock_job.id, {})
        if res.get("success") and res.get("file_path"):
            return [res["file_path"]]
        raise AutomationError(res.get("error") or "Single generation failed")
