from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

def list_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERRO: GEMINI_API_KEY não encontrada.")
        return

    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1alpha"}
    )

    print("\n--- TESTE v1 ---")
    client_v1 = genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options={"api_version": "v1"})
    try:
        models_v1 = [m.name for m in client_v1.models.list()]
        print(f"Modelos v1: {len(models_v1)}")
        if "models/gemini-2.0-flash" in models_v1: print("  gemini-2.0-flash DISPONÍVEL em v1")
    except Exception as e:
        print(f"Erro v1: {e}")

    print("\n--- TESTE v1alpha ---")
    client_alpha = genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options={"api_version": "v1alpha"})
    try:
        models_alpha = [m.name for m in client_alpha.models.list()]
        print(f"Modelos v1alpha: {len(models_alpha)}")
        if "models/gemini-2.0-flash" in models_alpha: print("  gemini-2.0-flash DISPONÍVEL em v1alpha")
    except Exception as e:
        print(f"Erro v1alpha: {e}")




                
    except Exception as e:
        print(f"Erro ao listar modelos: {e}")

if __name__ == "__main__":
    list_models()
