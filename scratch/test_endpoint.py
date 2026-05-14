import requests
try:
    r = requests.get("http://localhost:3333/api/config")
    print(r.json())
except Exception as e:
    print(f"Error: {e}")
