# utils.py  v6.0
"""
Helper utilities for Google Flow Studio Batch Pro.
Handles slugification, JSON validation/normalization, prompt construction with @Character tags, and filename rendering.
"""

import re
import unicodedata

MAX_SLUG_CHARS   = 60
MAX_FILENAME_LEN = 180


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = s.encode("ascii", "ignore").decode("ascii").lower().strip()
    s = re.sub(r"['\"]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s or "item"


def _trunc_slug(slug: str, max_len: int = MAX_SLUG_CHARS) -> str:
    if len(slug) <= max_len:
        return slug
    cut = slug[:max_len]
    last = cut.rfind("-")
    if last > max_len // 2:
        cut = cut[:last]
    return cut.strip("-") or slug[:max_len]


def normalize_json(raw) -> dict:
    """
    Accept multiple JSON formats and normalise to {"topics": [...]}.

    Format A (wrapped object):
        {"topics": [{"name": "...", "prompts": ["..."]}]}

    Format B (bare array of topics):
        [{"name": "...", "prompts": ["..."]}]

    Format C (detailed with character/model):
        {"character": "Elena", "model": "Nano Banana", "topics": [...]}
    """
    if isinstance(raw, list):
        return {"topics": raw}
    return raw


def validate_json(data) -> str:
    """Validate normalised data structure."""
    if not isinstance(data, dict):
        return "Root must be a JSON object or array."
    if not isinstance(data.get("topics"), list):
        return 'Missing "topics" array.'
    for i, t in enumerate(data["topics"]):
        if not isinstance(t, dict):
            return f"Topic #{i+1} must be an object."
        if not isinstance(t.get("name"), str) or not t["name"].strip():
            return f"Topic #{i+1} missing 'name'."
        if not isinstance(t.get("prompts"), list):
            return f'Topic "{t["name"]}" missing "prompts" array.'
        for j, p in enumerate(t["prompts"]):
            if isinstance(p, dict):
                # Prompt can be an object with prompt text, character override, etc.
                text = p.get("text") or p.get("prompt")
                if not text or not str(text).strip():
                    return f'Topic "{t["name"]}" prompt #{j+1} object must contain non-empty "text" or "prompt".'
            elif not isinstance(p, str) or not p.strip():
                return f'Topic "{t["name"]}" prompt #{j+1} must be a non-empty string.'
    return ""


def generate_filename(template: str, job, max_slug: int = MAX_SLUG_CHARS, mode: str = "image") -> str:
    from datetime import date
    d = date.today()
    ds = f"{d.year}-{d.month:02d}-{d.day:02d}"
    ts = _trunc_slug(job.topic_slug or slugify(job.topic_name), max_slug)
    ps = _trunc_slug(job.prompt_slug or slugify(job.prompt_text), max_slug)
    cs = _trunc_slug(slugify(getattr(job, "character_name", "")), max_slug) or "nochar"

    mapping = {
        "{topicSlug}":     ts,
        "{topicName}":     job.topic_name,
        "{topicIndex}":    str(job.topic_index),
        "{promptIndex}":   str(job.prompt_index),
        "{globalIndex}":   str(job.global_index),
        "{promptSlug}":    ps,
        "{characterSlug}": cs,
        "{date}":          ds,
    }

    ext = ".mp4" if getattr(job, "mode", mode) == "video" else ".png"
    out = template or "{topicSlug}/{topicSlug}_{promptIndex}_{promptSlug}.png"
    for k, v in mapping.items():
        out = out.replace(k, v)
    out = re.sub(r"(\.\.[/\\])", "", out)
    out = re.sub(r'[<>:"|?*\x00-\x1f]', "_", out)

    # Ensure right extension
    if not re.search(r'\.(png|jpg|jpeg|webp|mp4)$', out, re.I):
        out += ext
    else:
        # Replace .png with .mp4 if video mode
        if getattr(job, "mode", mode) == "video" and not out.lower().endswith(".mp4"):
            out = re.sub(r'\.(png|jpg|jpeg|webp)$', '.mp4', out, flags=re.I)

    parts = out.replace("\\", "/").split("/")
    fname = parts[-1]
    if len(fname) > MAX_FILENAME_LEN:
        stem, fext = (fname.rsplit(".", 1) if "." in fname else (fname, ext.strip(".")))
        parts[-1] = f"{stem[:MAX_FILENAME_LEN-len(fext)-1]}.{fext}"
    return "/".join(parts)


def build_final_prompt(
    base: str,
    character_name: str = "",
    prefix: str = "",
    suffix: str = "",
    style: str = "",
    aspect_ratio: str = "",
    negative_prompt: str = "",
    cinematic_style: str = "",
    character_consistency: str = "",
    environment_consistency: str = "",
) -> str:
    """
    Synthesize prompt for Google Flow with Character Consistency tagging (@Character).
    """
    parts = []

    # 1. Attach character tag if provided (e.g., @Elena)
    if character_name and character_name.strip():
        tag = character_name.strip()
        if not tag.startswith("@"):
            tag = f"@{tag.replace(' ', '')}"
        parts.append(tag)

    # 2. Add custom prompt prefix
    if prefix.strip():
        parts.append(prefix.strip().rstrip(",") + ",")

    # 3. Add base prompt
    parts.append(base.strip())

    # 4. Add custom suffix
    if suffix.strip():
        parts.append("," + suffix.strip())

    # 5. Add style preset
    if style.strip():
        parts.append(f", style: {style.strip()}")

    if cinematic_style.strip():
        parts.append(f", {cinematic_style.strip()}")

    if environment_consistency.strip():
        parts.append(f", {environment_consistency.strip()}")

    if character_consistency.strip() and not character_name.strip():
        parts.append(f", {character_consistency.strip()}")

    # 6. Negative Prompt
    if negative_prompt.strip():
        parts.append(f", avoiding: {negative_prompt.strip()}")

    return " ".join(parts)


def format_duration(s: float) -> str:
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_rate(done: int, elapsed: float) -> str:
    if not done or not elapsed:
        return "—"
    spi = elapsed / done
    return f"{spi:.0f}s/item" if spi < 60 else f"{spi/60:.1f}m/item"


def eta_string(pending: int, elapsed: float, done: int) -> str:
    if not done or not pending:
        return "—"
    secs = int((elapsed / done) * pending)
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"
