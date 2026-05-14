import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Definindo as ferramentas conforme o types.ts (SDK 1.0 style)
tools = [
    {
        "name": "launch_app",
        "description": "Abre um aplicativo Windows pelo nome (ex: 'notepad', 'chrome', 'calc').",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nome do app"}
            },
            "required": ["name"]
        }
    }
]

model_id = "gemini-2.0-flash"
sys_instruct = "Você é o Jarvis. Se o usuário pedir para abrir o bloco de notas, use a ferramenta launch_app(name='notepad'). Fale sempre em português."

response = client.models.generate_content(
    model=model_id,
    contents="Jarvis, abra o bloco de notas",
    config={
        "system_instruction": sys_instruct,
        "tools": tools
    }
)

print(f"Resposta: {response.text}")
if response.candidates[0].content.parts:
    for part in response.candidates[0].content.parts:
        if part.call:
            print(f"Chamada de Função: {part.call.name} com args: {part.call.args}")
