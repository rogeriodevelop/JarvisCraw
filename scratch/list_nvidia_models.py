import os
from openai import AsyncOpenAI
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def list_nvidia_models():
    client = AsyncOpenAI(
        api_key=os.getenv("NVIDIA_API_KEY"),
        base_url="https://integrate.api.nvidia.com/v1"
    )
    models = await client.models.list()
    for m in models.data:
        print(m.id)

if __name__ == "__main__":
    asyncio.run(list_nvidia_models())
