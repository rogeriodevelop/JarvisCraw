import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("GEMINI_API_KEY not found")
    exit(1)

client = genai.Client(api_key=api_key)

def hello_tool(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

model_id = "gemini-2.0-flash"

try:
    print(f"Testing model: {model_id} with tools via REST...")
    response = client.models.generate_content(
        model=model_id,
        contents="Say hello to Rogerio using the tool.",
        config=types.GenerateContentConfig(
            tools=[hello_tool],
            temperature=0.0
        )
    )
    
    print("Response received!")
    if response.candidates:
        candidate = response.candidates[0]
        if candidate.content.parts:
            for part in candidate.content.parts:
                if part.call:
                    print(f"Tool call detected: {part.call.name} with args {part.call.args}")
                elif part.text:
                    print(f"Text response: {part.text}")
        else:
            print("No parts in response.")
    else:
        print("No candidates in response.")

except Exception as e:
    print(f"Error testing Gemini: {e}")
