from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from automator import (
    FLOW_INPUT_SELECTORS,
    FLOW_GENERATE_BUTTON_SELECTORS,
    FLOW_MEDIA_SELECTORS,
    _FLOW_PAGE_STATE_JS,
    GoogleFlowAutomator
)
from models import Settings

def test_selectors_structure():
    assert len(FLOW_INPUT_SELECTORS) >= 5
    assert len(FLOW_GENERATE_BUTTON_SELECTORS) >= 5
    assert len(FLOW_MEDIA_SELECTORS) >= 5
    assert "isGenerating" in _FLOW_PAGE_STATE_JS
    assert "goodMediaCount" in _FLOW_PAGE_STATE_JS

def test_automator_init():
    cfg = Settings()
    auto = GoogleFlowAutomator(
        profile_dir="profiles/test",
        settings=cfg,
        account_name="Test Account"
    )
    assert auto._acct_name == "Test Account"
    assert auto.running is True
    assert auto._is_flow_page("https://flow.google.com/tools/flow") is True

@pytest.mark.anyio
async def test_automator_run_prompt_multiple_images(tmp_path):
    cfg = Settings()
    auto = GoogleFlowAutomator(
        profile_dir=str(tmp_path / "profile"),
        settings=cfg,
        account_name="Test Account"
    )

    # Mock methods
    auto._wait_for_input = AsyncMock(return_value=True)
    auto._configure_generation_settings = AsyncMock()
    auto._get_state = AsyncMock(return_value={"mediaCount": 0, "mediaSrcs": []})
    auto._type_prompt = AsyncMock()
    auto._submit_generation = AsyncMock()
    auto._page = AsyncMock()
    auto._page.url = "https://flow.google.com/project/123"

    mock_medias = [
        {"tag": "img", "src": "https://flow-content.google/img1.png", "w": 512, "h": 512},
        {"tag": "img", "src": "https://flow-content.google/img2.png", "w": 512, "h": 512},
        {"tag": "img", "src": "https://flow-content.google/img3.png", "w": 512, "h": 512},
    ]
    auto._wait_for_generation = AsyncMock(return_value=mock_medias)

    async def fake_download(media_info, target_path):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"fake image data 12345678901234567890")
        return True

    auto._download_media = AsyncMock(side_effect=fake_download)

    save_path = tmp_path / "output" / "01.png"
    saved = await auto.run_prompt(
        prompt_text="Test prompt",
        save_path=save_path,
        image_count="x3"
    )

    assert len(saved) == 3
    assert saved[0] == str(save_path)
    assert saved[1] == str(tmp_path / "output" / "01_2.png")
    assert saved[2] == str(tmp_path / "output" / "01_3.png")
    assert (tmp_path / "output" / "01.png").exists()
    assert (tmp_path / "output" / "01_2.png").exists()
    assert (tmp_path / "output" / "01_3.png").exists()

@pytest.mark.anyio
async def test_automator_run_prompt_recovers_focus_without_new_project(tmp_path):
    cfg = Settings()
    auto = GoogleFlowAutomator(
        profile_dir=str(tmp_path / "profile"),
        settings=cfg,
        account_name="Test Account"
    )

    # First wait_for_input returns False, then after recover_prompt_focus returns True
    auto._wait_for_input = AsyncMock(side_effect=[False, True])
    auto._recover_prompt_focus = AsyncMock()
    auto.new_project_or_session = AsyncMock()
    auto._configure_generation_settings = AsyncMock()
    auto._get_state = AsyncMock(return_value={"mediaCount": 0, "mediaSrcs": []})
    auto._type_prompt = AsyncMock()
    auto._submit_generation = AsyncMock()
    auto._page = AsyncMock()
    auto._page.url = "https://flow.google.com/project/123"

    mock_medias = [
        {"tag": "img", "src": "https://flow-content.google/img1.png", "w": 512, "h": 512},
    ]
    auto._wait_for_generation = AsyncMock(return_value=mock_medias)
    auto._download_media = AsyncMock(return_value=True)

    save_path = tmp_path / "output" / "01.png"
    saved = await auto.run_prompt(
        prompt_text="Test prompt",
        save_path=save_path,
        do_new_session=False
    )

    assert len(saved) == 1
    # Verify new_project_or_session was NOT called
    auto.new_project_or_session.assert_not_called()
    # Verify _recover_prompt_focus WAS called
    auto._recover_prompt_focus.assert_called_once()


