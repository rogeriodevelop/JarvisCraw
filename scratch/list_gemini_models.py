import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

def list_gemini_models():
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
    
    print("--- Todos os Modelos (v1alpha) ---")
    for model in client.models.list():
        print(f"ID: {model.name} | Methods: {model.supported_actions}")

if __name__ == "__main__":
    list_gemini_models()
