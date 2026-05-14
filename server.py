"""VoiceClaw backend — FastAPI server with WebSocket for Claude events."""

import argparse
import asyncio
import json
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from checkpoint import GitCheckpoint, SessionManager
from agent_runner import AgentRunner
from context_bridge import ContextBridge
from function_router import FunctionRouter
from gemini_session import create_ephemeral_token
from stt_service import transcribe_audio

load_dotenv()

app = FastAPI(title="VoiceClaw")

# Global state
project_dir: str | None = None
agent_runner: AgentRunner | None = None
function_router: FunctionRouter | None = None
context_bridge = ContextBridge()
session_manager: SessionManager | None = None
git_checkpoint: GitCheckpoint | None = None


def set_project(path: str):
    """Initialize all components for a project directory."""
    global project_dir, agent_runner, function_router, session_manager, git_checkpoint

    project_dir = path
    session_manager = SessionManager(project_dir)
    agent_runner = AgentRunner(project_dir)
    function_router = FunctionRouter(agent_runner)
    git_checkpoint = GitCheckpoint(project_dir)

    # Restore agent session ID if available
    if session_manager.agent_session_id:
        agent_runner.session_id = session_manager.agent_session_id
    
    # Restore agent model and effort if saved
    if session_manager.agent_model:
        agent_runner.model = session_manager.agent_model
        print(f"DEBUG: Restored agent model: {agent_runner.model}")
    if session_manager.agent_effort:
        agent_runner.effort = session_manager.agent_effort

    print(f"Project set: {project_dir}")


# ── REST Endpoints ────────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {"status": "ok", "project": project_dir}


@app.get("/api/project")
async def get_project():
    return {"path": project_dir, "active": project_dir is not None}


@app.post("/api/project")
async def set_project_endpoint(data: dict):
    path = data.get("path", "").strip()
    if not path:
        return JSONResponse({"error": "Path is required"}, status_code=400)

    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        return JSONResponse({"error": "Directory not found"}, status_code=400)

    set_project(str(resolved))
    return {"ok": True, "path": project_dir}


@app.get("/api/projects/browse")
async def browse_dirs(path: str = "~"):
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        return JSONResponse({"error": "Not a directory"}, status_code=400)

    dirs = []
    try:
        for d in sorted(resolved.iterdir(), key=lambda x: x.name.lower()):
            if d.is_dir() and not d.name.startswith("."):
                dirs.append({"name": d.name, "path": str(d)})
    except PermissionError:
        pass

    return {
        "current": str(resolved),
        "parent": str(resolved.parent),
        "dirs": dirs,
    }


@app.get("/api/projects/pick")
async def pick_directory():
    """Open native OS folder picker dialog."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory()
    root.destroy()

    if not path:
        return {"path": None}
    return {"path": path}


@app.get("/api/token")
async def get_token():
    return create_ephemeral_token()


@app.get("/api/config")
async def get_config():
    prompt_path = Path(__file__).parent / "prompts" / "gemini_system.md"
    system_prompt = ""
    if prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    return {
        "system_prompt": system_prompt,
        "model": "models/gemini-2.5-flash-native-audio-latest",
        "nvidia_api_key": os.getenv("NVIDIA_API_KEY"),
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY"),
    }


@app.get("/api/models")
async def list_available_models():
    """List available models from all providers"""
    google_models = [
        {"id": "models/gemini-2.5-flash-native-audio-latest", "name": "Gemini 2.5 Flash Live (Voz + Tools)", "provider": "google"},
        {"id": "models/gemini-3.1-flash-live-preview", "name": "Gemini 3.1 Flash Live (Novo)", "provider": "google"},
        {"id": "models/gemini-2.0-flash", "name": "Gemini 2.0 Flash (Texto Only)", "provider": "google"},
        {"id": "models/gemini-1.5-flash", "name": "Gemini 1.5 Flash (Estável)", "provider": "google"},
    ]

    nvidia_models = []
    nv_key = os.getenv("NVIDIA_API_KEY")
    if nv_key:
        nvidia_models = [
            {"id": "nvidia/meta/llama-3.3-70b-instruct", "name": "Llama 3.3 70B (NVIDIA)", "provider": "nvidia"},
            {"id": "nvidia/meta/llama-3.1-70b-instruct", "name": "Llama 3.1 70B (NVIDIA)", "provider": "nvidia"},
            {"id": "nvidia/deepseek-ai/deepseek-v4-pro", "name": "DeepSeek V4 Pro (NVIDIA)", "provider": "nvidia"},
            {"id": "nvidia/nvidia/llama-3.1-nemotron-70b-instruct", "name": "Nemotron 70B (NVIDIA)", "provider": "nvidia"},
        ]

    openrouter_models = []
    or_key = os.getenv("OPENROUTER_API_KEY")
    if or_key:
        openrouter_models = [
            {"id": "openrouter/anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet (OpenRouter)", "provider": "openrouter"},
            {"id": "openrouter/openai/gpt-4o", "name": "GPT-4o (OpenRouter)", "provider": "openrouter"},
            {"id": "openrouter/deepseek/deepseek-chat", "name": "DeepSeek V3 (OpenRouter)", "provider": "openrouter"},
            {"id": "openrouter/google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash (OpenRouter)", "provider": "openrouter"},
        ]

    return {"models": google_models + nvidia_models + openrouter_models}


@app.get("/api/narration-config")
async def get_narration_config():
    prompt_path = Path(__file__).parent / "prompts" / "narration_system.md"
    system_prompt = ""
    if prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    return {
        "system_prompt": system_prompt,
        "model": "gemini-2.5-flash-native-audio-latest",
    }


@app.get("/api/session")
async def get_session():
    if not session_manager:
        return {"gemini_handle": None, "agent_session_id": None}
    return {
        "gemini_handle": session_manager.gemini_handle,
        "agent_session_id": session_manager.agent_session_id,
    }


@app.post("/api/session")
async def update_session(data: dict):
    if session_manager and "gemini_handle" in data:
        session_manager.gemini_handle = data["gemini_handle"]
    return {"ok": True}


@app.post("/api/transcribe")
async def transcribe(request: Request):
    """Transcribe audio via Gemini generateContent. Runs in parallel with Live API."""
    try:
        data = await request.json()
        chunks = data.get("audio_chunks", [])
        language = data.get("language", "en-US")
        if not chunks:
            return {"transcript": ""}
        transcript = await transcribe_audio(chunks, language)
        return {"transcript": transcript}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"transcript": "", "error": str(e)}, status_code=200)


@app.post("/api/agent-config")
async def set_agent_config(request: Request):
    if not agent_runner:
        return JSONResponse({"error": "No project selected"}, status_code=400)

    data = await request.json()
    model = data.get("model", "").strip()
    effort = data.get("effort", "").strip()

    if model:
        agent_runner.model = model
        if session_manager:
            session_manager.agent_model = model
    if effort:
        agent_runner.effort = effort
        if session_manager:
            session_manager.agent_effort = effort

    return {"model": agent_runner.model, "effort": agent_runner.effort}


@app.get("/api/agent-config")
async def get_agent_config():
    if not agent_runner:
        return {"model": "google/gemini-2.0-flash", "effort": "high"}
    return {"model": agent_runner.model, "effort": agent_runner.effort}


@app.get("/api/checkpoints")
async def list_checkpoints():
    if not git_checkpoint:
        return {"checkpoints": [], "error": "No project selected"}
    return {"checkpoints": git_checkpoint.list_checkpoints()}


@app.post("/api/checkpoints/restore")
async def restore_checkpoint(request: Request):
    if not git_checkpoint:
        return JSONResponse({"error": "No project selected"}, status_code=400)
    data = await request.json()
    commit_hash = data.get("hash", "").strip()
    if not commit_hash:
        return JSONResponse({"error": "No commit hash provided"}, status_code=400)
    result = git_checkpoint.restore(commit_hash)
    if not result["ok"]:
        return JSONResponse(result, status_code=400)
    return result


@app.get("/api/context")
async def get_context():
    return {"summary": context_bridge.get_summary()}


# ── WebSocket ─────────────────────────────────────────────────


@app.post("/api/cancel")
async def cancel_agent():
    """Kill any running agent operation."""
    if agent_runner:
        try:
            await agent_runner.cancel()
            return {"ok": True, "message": "Agent operation cancelled"}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True, "message": "No operation running"}


async def handle_function_call(websocket: WebSocket, msg: dict):
    """Process a function call from Gemini via the browser relay."""
    print(f"DEBUG WS: Received function_call: {msg.get('name')} with args: {msg.get('args')}")
    
    if not function_router:
        print("DEBUG WS: No project selected, sending error")
        await websocket.send_json({
            "type": "function_result",
            "id": msg.get("id"),
            "name": msg.get("name"),
            "result": "No project selected. Please select a project folder first.",
            "is_error": True,
        })
        return

    call_id = msg["id"]
    name = msg["name"]
    args = msg.get("args", {})

    print(f"DEBUG WS: Processing {name} with args: {args}")

    # Git checkpoint before write operations
    if name in ("code_task", "run_command") and git_checkpoint:
        git_checkpoint.create(label=f"{name}: {str(args)[:60]}")

    event_count = 0
    try:
        async for event in function_router.route(name, args):
            event_count += 1
            print(f"DEBUG WS: Sending event #{event_count}: {event.get('type')} - {event.get('subtype', '')}")
            
            # Attach function call metadata to the final result
            if event.get("type") == "function_result":
                event["id"] = call_id
                event["name"] = name

                # Store in context bridge
                context_bridge.store(name, args, event.get("result", ""))

                # Update session ID
                if session_manager and event.get("session_id"):
                    session_manager.agent_session_id = event["session_id"]

            try:
                await websocket.send_json(event)
                print(f"DEBUG WS: Event #{event_count} sent successfully")
            except Exception as e:
                print(f"DEBUG WS: Error sending event #{event_count}: {e}")
                break
                
        print(f"DEBUG WS: Finished processing {name}, sent {event_count} events")
    except Exception as e:
        print(f"DEBUG WS: Exception in handle_function_call: {e}")
        import traceback
        traceback.print_exc()
        # Send error to client
        try:
            await websocket.send_json({
                "type": "function_result",
                "id": call_id,
                "name": name,
                "result": f"Error processing function: {str(e)}",
                "is_error": True,
            })
        except:
            pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "function_call":
                asyncio.create_task(handle_function_call(websocket, msg))
            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ── Static files ──────────────────────────────────────────────

static_dir = Path(__file__).parent / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True))


# ── Main ──────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="VoiceClaw server")
    parser.add_argument(
        "--project",
        default=None,
        help="Project directory for Claude Code (optional — can select in browser)",
    )
    parser.add_argument("--port", type=int, default=3333, help="Server port")
    args = parser.parse_args()

    if args.project:
        set_project(os.path.abspath(args.project))

    print(f"VoiceClaw starting on http://localhost:{args.port}")
    
    # Check providers
    providers = []
    if os.getenv("GEMINI_API_KEY"): providers.append("Google")
    if os.getenv("NVIDIA_API_KEY"): providers.append("NVIDIA")
    if os.getenv("OPENROUTER_API_KEY"): providers.append("OpenRouter")
    print(f"Active Providers: {', '.join(providers) if providers else 'None (Check .env)'}")

    if project_dir:
        print(f"Project directory: {project_dir}")
    else:
        print("No project selected — select one in the browser")

    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
