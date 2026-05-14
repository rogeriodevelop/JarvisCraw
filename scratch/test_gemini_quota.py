import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

models_to_test = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-2.0-flash-lite-preview-02-05",
    "gemini-1.5-pro"
]

for model_id in models_to_test:
    try:
        print(f"Testing {model_id}...")
        response = client.models.generate_content(
            model=model_id,
            contents="Say 'OK' if you can hear me.",
        )
        print(f"Success for {model_id}!")
    except Exception as e:
        print(f"Failed for {model_id}: {e}")
