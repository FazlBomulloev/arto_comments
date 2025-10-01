
from src.cfg import config
from mistralai import Mistral, UserMessage, SystemMessage
import asyncio

async def request(agent_id: str, content: str):
    """Отправляет запрос к конкретному агенту Mistral AI"""
    async with Mistral(api_key=config.AI_TOKEN) as mistral:
        try:
            response = await mistral.agents.complete_async(
                messages=[UserMessage(content=content)],
                stream=False,
                agent_id=agent_id
            )
            return response.choices[0].message.content if response.choices else None
        except Exception as e:
            print(f"API Error: {e}")
            raise