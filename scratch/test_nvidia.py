import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("NVIDIA_API_KEY")
if not api_key:
    print("NVIDIA_API_KEY not found")
    exit(1)

# List available models from NVIDIA to find correct IDs
url = "https://integrate.api.nvidia.com/v1/models"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json"
}

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    models = response.json().get("data", [])
    print("Available NVIDIA models:")
    for m in models:
        print(f"- {m['id']}")
except Exception as e:
    print(f"Error listing models: {e}")

# Test a single completion with a known model to verify 404
test_model = "meta/llama-3.3-70b-instruct"
url = "https://integrate.api.nvidia.com/v1/chat/completions"
payload = {
    "model": test_model,
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 10
}

try:
    print(f"\nTesting model: {test_model}")
    response = requests.post(url, headers=headers, json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Error: {response.text}")
    else:
        print("Success!")
except Exception as e:
    print(f"Error testing model: {e}")
