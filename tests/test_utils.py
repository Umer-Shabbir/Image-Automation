from utils import build_final_prompt, generate_filename, normalize_json, validate_json
from models import Job, Settings

def test_build_final_prompt():
    res = build_final_prompt("A man walking", "Elena", "Photo of", "vintage", "cinematic", "16:9")
    assert "@Elena" in res
    assert "Photo of" in res
    assert "vintage" in res
    assert "cinematic" in res

def test_generate_filename_image():
    j = Job(topic_slug="city", prompt_index=1, prompt_slug="neon", mode="image")
    name = generate_filename("out/{topicSlug}_{promptSlug}.png", j)
    assert name.endswith(".png")
    assert "city" in name
    assert "neon" in name

def test_generate_filename_video():
    j = Job(topic_slug="city", prompt_index=1, prompt_slug="neon", mode="video")
    name = generate_filename("out/{topicSlug}_{promptSlug}.png", j, mode="video")
    assert name.endswith(".mp4")
