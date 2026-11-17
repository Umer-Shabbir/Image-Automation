"""
Image validation utility using Anthropic Claude Vision API.
"""

import base64
import asyncio
import os
from typing import Optional
import httpx
from anthropic import AsyncAnthropic


async def validate_image(
    image_path: str,
    prompt: str,
    api_key: Optional[str] = None,
    model_name: str = "claude-3-haiku-20240307"
) -> bool:
    """
    Validates whether an image matches the intended prompt using Claude Vision.
    Falls back to ANTHROPIC_API_KEY or VALIDATION_API_KEY environment variables if api_key is omitted.
    """
    try:
        resolved_key = (api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("VALIDATION_API_KEY") or "").strip()
        if not resolved_key:
            return False

        client = AsyncAnthropic(api_key=resolved_key)
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        message = await client.messages.create(
            model=model_name,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"Does this image accurately reflect this prompt: '{prompt}'? Reply ONLY with 'YES' or 'NO'."
                        }
                    ]
                }
            ]
        )
        reply = message.content[0].text.strip().upper()
        return "YES" in reply
    except Exception:
        return False
