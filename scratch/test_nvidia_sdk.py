import os
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

async def test_nvidia_tools():
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        print("NVIDIA_API_KEY not found")
        return

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://integrate.api.nvidia.com/v1"
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "run_bash_command",
                "description": "Execute a bash command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"}
                    },
                    "required": ["command"]
                }
            }
        }
    ]

    messages = [
        {"role": "system", "content": "You are JARVIS. Answer queries."},
        {"role": "user", "content": "What is 2+2?"}
    ]

    model = "meta/llama-3.3-70b-instruct"

    try:
        print(f"Sending request to NVIDIA using {model} with tools...")
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            temperature=0.0,
        )
        print("Success! Response received.")
        print(response.choices[0].message)
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(test_nvidia_tools())
