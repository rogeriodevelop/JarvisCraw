import asyncio
import os
import sys
import json
from agent_runner import AgentRunner
from dotenv import load_dotenv

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

async def test_search():
    runner = AgentRunner(os.getcwd())
    runner.model = "google/gemini-2.0-flash"
    
    print(f"Testing task with provider {runner.model}...")
    try:
        async for event in runner.run("Qual a cotação do dólar hoje?"):
            etype = event.get("type")
            if etype == "agent_event":
                subtype = event.get("subtype")
                text = event.get('text', '')
                tool = event.get('tool', '')
                inp = event.get('input', '')
                if subtype == "thinking":
                    print(f"[JARVIS Thinking] {text}")
                elif subtype == "tool_use":
                    print(f"[JARVIS Tool Use] {tool}({inp})")
            elif etype == "status":
                text = event.get('text', f"Agent Running: {event.get('agent_running')}")
                print(f"[STATUS] {text}")
            elif etype == "function_result":
                res = event.get('result', '')
                err = event.get('is_error', False)
                print(f"\n[FINAL RESULT] {'(ERROR) ' if err else ''}{res}")
    except Exception as e:
        print(f"\nTest loop crashed with: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_search())
