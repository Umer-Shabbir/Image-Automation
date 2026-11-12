import base64
import asyncio
import httpx
from anthropic import AsyncAnthropic

async def validate_image(image_path: str, prompt: str, api_key: str, model_name: str = 'claude-3-haiku-20240307') -> bool:
    try:
        client = AsyncAnthropic(api_key=api_key)
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
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
        return 'YES' in reply
    except Exception as e:
        return False

