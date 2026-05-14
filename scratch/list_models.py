import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

def list_models():
    client = genai.Client(http_options={"api_version": "v1alpha"})
    with open("scratch/models_list.txt", "w", encoding="utf-8") as f:
        try:
            for m in client.models.list():
                f.write(f"ID: {m.name}, Name: {m.display_name}\n")
        except Exception as e:
            f.write(f"Error listing models: {e}\n")

if __name__ == "__main__":
    list_models()
