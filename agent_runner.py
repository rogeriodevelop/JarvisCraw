import asyncio
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import AsyncGenerator, List, Dict, Any

# Google SDK
from google import genai
from google.genai import types

# OpenAI SDK (for NVIDIA and OpenRouter)
from openai import AsyncOpenAI

# Obsidian memory bridge
from obsidian_bridge import ObsidianBridge

def run_bash_command(command: str, cwd: str = None) -> str:
    """Runs a bash/shell command and returns its stdout and stderr."""
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120, cwd=cwd)
        return f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}\nEXIT_CODE: {res.returncode}"
    except Exception as e:
        return f"Error: {str(e)}"

def read_file(path: str) -> str:
    """Reads the contents of a file."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception as e:
        return f"Error: {str(e)}"

def write_file(path: str, content: str) -> str:
    """Writes content to a file. Overwrites if exists."""
    try:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error: {str(e)}"

def list_directory(directory: str = ".") -> str:
    """Lists files and directories in the given path."""
    try:
        items = os.listdir(directory)
        return "\n".join(items) if items else "(empty directory)"
    except Exception as e:
        return f"Error: {str(e)}"

def create_directory(path: str) -> str:
    """Creates a directory and all parent directories."""
    try:
        os.makedirs(path, exist_ok=True)
        return f"Successfully created directory: {path}"
    except Exception as e:
        return f"Error: {str(e)}"

def computer_control(action: str, x: int = None, y: int = None, text: str = None, key: str = None, keys: list = None) -> str:
    """Controls the mouse and keyboard using PyAutoGUI."""
    import pyautogui
    import os
    
    # Create params dict for internal logic compatibility if needed
    params = {"x": x, "y": y, "text": text, "key": key, "keys": keys}
    
    # Fail-safe to top-left corner
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.5
    
    try:
        # Cast coordinates to int if provided
        if x is not None: x = int(x)
        if y is not None: y = int(y)
        if action == "screenshot":
            path = "scratch/last_screenshot.png"
            os.makedirs("scratch", exist_ok=True)
            pyautogui.screenshot(path)
            
            # Get logical resolution
            w, h = pyautogui.size()
            
            # Open image to check physical resolution
            from PIL import Image
            img = Image.open(path)
            if img.width != w or img.height != h:
                # Resize to logical resolution so coordinates match 1:1 for the model
                img = img.resize((w, h), Image.Resampling.LANCZOS)
                img.save(path)
            
            import base64
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                
            return f"SCREENSHOT_DATA:{b64}|RES:{w}x{h}"
        
        elif action == "click":
            pyautogui.click(x=x, y=y)
            return f"Clicked successfully at ({x}, {y})."
        
        elif action == "double_click":
            pyautogui.doubleClick(x=x, y=y)
            return f"Double-clicked successfully at ({x}, {y})."
        
        elif action == "type":
            pyautogui.write(text, interval=0.1)
            return f"Typed text: '{text}'"
        
        elif action == "press":
            pyautogui.press(key)
            return f"Pressed key: '{key}'"
            
        elif action == "hotkey":
            pyautogui.hotkey(*keys)
            return f"Pressed hotkey: {'+'.join(keys)}"

        elif action == "move":
            pyautogui.moveTo(x, y, duration=0.5)
            return f"Moved mouse to ({x}, {y})"

        return f"Unknown action: {action}"
    except Exception as e:
        return f"Error in computer_control: {str(e)}"

def launch_app(name: str) -> str:
    """Launches a Windows application, URL or document by name/path."""
    import subprocess
    try:
        # On Windows, 'start "" "target"' is the most robust way to handle spaces
        # and different types of targets (exe, url, doc).
        subprocess.Popen(f'start "" "{name}"', shell=True)
        return f"Comando para abrir '{name}' enviado com sucesso."
    except Exception as e:
        return f"Erro ao tentar abrir '{name}': {str(e)}"

def manage_background_task(action: str, instruction: str, interval: int = 5) -> str:
    """Manages a background repeating task."""
    import threading
    import time
    
    if action == "start":
        def task_loop():
            log_path = "scratch/background_tasks.log"
            os.makedirs("scratch", exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.ctime()}] TASK_STARTED: {instruction}\n")
            
            while True:
                # In a real scenario, the agent would use its brain here.
                # For now, we simulate monitoring by logging periodic checks.
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{time.ctime()}] MONITORING: {instruction}\n")
                time.sleep(interval)
        
        thread = threading.Thread(target=task_loop, daemon=True)
        thread.start()
        return f"Tarefa de monitoramento iniciada: '{instruction}' a cada {interval} segundos. Verifique os logs em scratch/background_tasks.log"
    
    return f"Ação de background desconhecida: {action}"

# ── Obsidian Memory Tool Functions ────────────────────────────

_obsidian_instance: ObsidianBridge | None = None

def set_obsidian_instance(instance: ObsidianBridge | None):
    """Set the shared ObsidianBridge instance for tool functions."""
    global _obsidian_instance
    _obsidian_instance = instance

def remember_memory(content: str, category: str = "general", tags: str = "", project: str = "") -> str:
    """Save a memory/note to the Obsidian vault for persistent recall."""
    if not _obsidian_instance:
        return "Erro: Obsidian vault não configurado. Defina OBSIDIAN_VAULT_PATH no .env"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    return _obsidian_instance.remember(content, category, tag_list, project or None)

def recall_memory(query: str) -> str:
    """Search and recall memories from the Obsidian vault."""
    if not _obsidian_instance:
        return "Erro: Obsidian vault não configurado. Defina OBSIDIAN_VAULT_PATH no .env"
    return _obsidian_instance.recall(query)

def search_memory(query: str) -> str:
    """Broad search across all memories in the Obsidian vault."""
    if not _obsidian_instance:
        return "Erro: Obsidian vault não configurado. Defina OBSIDIAN_VAULT_PATH no .env"
    return _obsidian_instance.search_memory(query)


# ── Subagent Delegation Tool Functions ─────────────────────────

_agent_runner_instance = None

def set_agent_runner_instance(instance):
    """Set the shared AgentRunner instance for tool delegation."""
    global _agent_runner_instance
    _agent_runner_instance = instance

def delegate_to_programmer(instruction: str) -> str:
    """Delega uma instrução de desenvolvimento de software fullstack complexa para o subagente especialista em programação sênior. Retorna a solução robusta e completa."""
    if not _agent_runner_instance:
        return "Erro: AgentRunner não inicializado para delegação."
    import asyncio
    import concurrent.futures
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(lambda: asyncio.run(_agent_runner_instance.run_programmer(instruction)))
            return future.result()
    else:
        return loop.run_until_complete(_agent_runner_instance.run_programmer(instruction))

def delegate_to_designer(instruction: str) -> str:
    """Delega uma instrução de criação de interface, design gráfico, estilo visual contemporâneo ou UX para o subagente especialista em design. Retorna a interface ou design completo."""
    if not _agent_runner_instance:
        return "Erro: AgentRunner não inicializado para delegação."
    import asyncio
    import concurrent.futures
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(lambda: asyncio.run(_agent_runner_instance.run_designer(instruction)))
            return future.result()
    else:
        return loop.run_until_complete(_agent_runner_instance.run_designer(instruction))

# Tool definitions for OpenAI style
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_bash_command",
            "description": "Runs a bash/shell command and returns its stdout and stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to run."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Writes content to a file. Overwrites if exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "content": {"type": "string", "description": "Content to write."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists files and directories in the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Path to list."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "computer_control",
            "description": "Control mouse and keyboard (Windows Desktop). Use 'screenshot' first to see coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string", 
                        "description": "Action: screenshot, click, type, press, hotkey, or move"
                    },
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "text": {"type": "string"},
                    "key": {"type": "string"},
                    "keys": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "Launch a Windows application (e.g. 'notepad', 'calc', 'chrome').",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Application name or command"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_background_task",
            "description": "Start a background repeating task or monitoring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["start", "stop"]},
                    "instruction": {"type": "string", "description": "What to check/do"},
                    "interval": {"type": "integer", "description": "Interval in seconds"}
                },
                "required": ["action", "instruction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Creates a directory and all parent directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to create."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remember_memory",
            "description": "Save a memory or note to the Obsidian vault for long-term persistent recall. Use to remember decisions, learnings, or important context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The information to remember (Markdown supported)"},
                    "category": {"type": "string", "enum": ["session", "project", "decision", "general"], "description": "Category of the memory"},
                    "tags": {"type": "string", "description": "Comma-separated tags for the note"},
                    "project": {"type": "string", "description": "Project name to link this memory to"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Search and recall memories from the Obsidian vault. Use to retrieve past decisions, context, or learnings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query to find relevant memories"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Broad search across all memories in the Obsidian vault. Returns more results than recall.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_programmer",
            "description": "Delega uma instrução de desenvolvimento de software fullstack complexa para o subagente especialista em programação sênior. Retorna a solução robusta e completa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {"type": "string", "description": "A instrução ou tarefa detalhada de programação para o especialista."}
                },
                "required": ["instruction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_designer",
            "description": "Delega uma instrução de criação de interface, design gráfico, estilo visual contemporâneo ou UX para o subagente especialista em design. Retorna a interface ou design completo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {"type": "string", "description": "A instrução detalhada de criação de design e UX para o especialista."}
                },
                "required": ["instruction"]
            }
        }
    }
]

class AgentRunner:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.session_id = None
        self.model = "google/gemini-2.0-flash"
        self.effort = "high"
        self._cancelled = False
        
        # Subagents Active Status
        self.programmer_active = False
        self.designer_active = False
        
        # Obsidian Memory
        vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
        if vault_path and Path(vault_path).exists():
            self.obsidian = ObsidianBridge(vault_path)
            set_obsidian_instance(self.obsidian)
            print(f"Obsidian vault connected: {vault_path}")
        else:
            self.obsidian = None
            # Fallback: use project-local brain directory
            local_brain = os.path.join(self.project_dir, ".voicecode", "brain")
            os.makedirs(local_brain, exist_ok=True)
            self.obsidian = ObsidianBridge(local_brain)
            set_obsidian_instance(self.obsidian)
            print(f"Obsidian vault (local fallback): {local_brain}")
        
        # Clients
        self.google_client = genai.Client()
        
        # NVIDIA Client
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        self.nvidia_client = AsyncOpenAI(
            api_key=nvidia_key,
            base_url="https://integrate.api.nvidia.com/v1"
        ) if nvidia_key else None
        # OpenRouter Client
        or_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_client = AsyncOpenAI(
            api_key=or_key,
            base_url="https://openrouter.ai/api/v1"
        ) if or_key else None
        
        # Memory / History
        self.history_file = os.path.join(self.project_dir, ".voicecode", "history.json")
        self.history = self._load_history()
        
        # Set agent runner global instance
        set_agent_runner_instance(self)

    def _load_history(self) -> list:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_history(self):
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                # Limit history size to prevent context overflow (keep last 50 messages)
                json.dump(self.history[-50:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")

    def _get_provider(self, model_id: str) -> str:
        if model_id.startswith("nvidia/"): return "nvidia"
        if model_id.startswith("openrouter/"): return "openrouter"
        if model_id.startswith("google/"): return "google"
        # If no prefix or contains gemini, it's Google
        if "gemini" in model_id.lower(): return "google"
        return "google"

    async def run(
        self,
        instruction: str,
        mode: str = "edit",
        allowed_tools: str | None = None,
        permission_mode: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        
        print(f"DEBUG run(): self.model = {self.model}")
        primary_provider = self._get_provider(self.model)
        print(f"DEBUG run(): primary_provider = {primary_provider}")
        providers_to_try = [primary_provider]
        
        # Determine fallback order
        if primary_provider == "google":
            if self.nvidia_client: providers_to_try.append("nvidia")
            if self.openrouter_client: providers_to_try.append("openrouter")
        elif primary_provider == "nvidia":
            providers_to_try.append("google")
            if self.openrouter_client: providers_to_try.append("openrouter")
            
        last_error = None
        for provider in providers_to_try:
            yield {"type": "status", "text": f"Iniciando tarefa com provedor: {provider.capitalize()}..."}
            success = False
            try:
                if provider == "google":

                    async for event in self._run_google(instruction, allowed_tools):
                        # Detect internal error in events
                        if event.get("type") == "function_result" and event.get("is_error"):
                            err_msg = str(event.get("result", ""))
                            if "429" in err_msg or "quota" in err_msg.lower():
                                raise Exception(f"Quota exceeded on Google: {err_msg}")
                        yield event
                    success = True
                else:
                    # Select a default model for the provider if the current one doesn't match
                    fallback_model = self.model
                    if provider == "nvidia" and not fallback_model.startswith("nvidia/"):
                        fallback_model = "nvidia/meta/llama-3.1-70b-instruct"
                    elif provider == "openrouter" and not fallback_model.startswith("openrouter/"):
                        fallback_model = "openrouter/anthropic/claude-3.5-sonnet"
                    elif provider == "google" and not fallback_model.startswith("google/"):
                        fallback_model = "google/gemini-2.0-flash"

                    async for event in self._run_openai_style(instruction, provider, allowed_tools, fallback_model):
                        if event.get("type") == "function_result" and event.get("is_error"):
                            err_msg = str(event.get("result", ""))
                            if "429" in err_msg or "quota" in err_msg.lower():
                                raise Exception(f"Quota exceeded on {provider}: {err_msg}")
                        yield event
                    success = True
                
                if success:
                    return # Completed successfully
                    
            except Exception as e:
                last_error = str(e)
                import traceback
                print(f"DEBUG: Provider {provider} failed with error: {last_error}")
                traceback.print_exc()
                
                # Check if it's a quota error
                is_quota_error = "429" in last_error or "quota" in last_error.lower() or "rate_limit" in last_error.lower() or "exceeded" in last_error.lower()
                
                if is_quota_error:
                    yield {
                        "type": "agent_event", 
                        "subtype": "thinking", 
                        "text": f"⚠️ Limite atingido no {provider}. Alternando para provedor de fallback..."
                    }
                else:
                    # Non-quota error - yield error info but don't fallback immediately
                    yield {
                        "type": "agent_event", 
                        "subtype": "thinking", 
                        "text": f"⚠️ Erro no {provider}: {last_error[:100]}. Tentando próximo provedor..."
                    }
                continue
                
        if not success:
            error_msg = f"Erro crítico: Todos os provedores falharam ou atingiram o limite. Último erro: {last_error}"
            print(f"DEBUG: Final error - {error_msg}")
            yield {"type": "function_result", "result": error_msg, "is_error": True, "session_id": self.session_id}

    async def _run_google(self, instruction: str, allowed_tools: str | None = None) -> AsyncGenerator[dict, None]:
        self.session_id = self.session_id or str(uuid.uuid4())
        self._cancelled = False
        
        yield {
            "type": "status",
            "agent_running": True,
            "session_id": self.session_id,
        }

        # Force a text-capable model if the audio-only model is requested for REST tasks
        actual_model = self.model.replace("google/", "")
        if "native-audio" in actual_model or "exp" in actual_model:
            # Fallback to a stable text model for tool-use tasks
            actual_model = "gemini-2.0-flash"

        
        
        full_instruction = f"You are working in directory: {self.project_dir}\n\nTask: {instruction}"
        
        # Add new user message to history
        self.history.append({"role": "user", "content": full_instruction})
        
        # Prepare messages for Gemini (map role names if needed)
        # Note: self.history stores generic roles, we convert them to Gemini types
        gemini_messages = []
        for msg in self.history:
            role = "user" if msg["role"] == "user" else "model"
            gemini_messages.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
        
        messages = gemini_messages
        
        # Tool filtering
        all_tools = [run_bash_command, read_file, write_file, list_directory, create_directory, computer_control, launch_app, manage_background_task, remember_memory, recall_memory, search_memory, delegate_to_programmer, delegate_to_designer]
        if allowed_tools:
            allowed_names = [t.strip().lower() for t in allowed_tools.split(",")]
            print(f"DEBUG: allowed_tools = {allowed_tools}, parsed names = {allowed_names}")
            # Map friendly names to actual functions
            mapping = {
                "bash": run_bash_command,
                "run_bash_command": run_bash_command,
                "read": read_file,
                "read_file": read_file,
                "write": write_file,
                "write_file": write_file,
                "ls": list_directory,
                "list_directory": list_directory,
                "glob": list_directory, # Alias common in LLM system prompts
                "grep": run_bash_command, # Grep is handled via bash
                "google_search": "google_search",
                "search": "google_search",
                "computer_control": computer_control,
                "computer_use": computer_control,
                "screenshot": computer_control,
                "mouse": computer_control,
                "click": computer_control,
                "launch_app": launch_app,
                "open_app": launch_app,
                "open_url": launch_app,
                "background_task": manage_background_task,
                "monitor": manage_background_task,
                "create_directory": create_directory,
                "mkdir": create_directory,
                "delegate_to_programmer": delegate_to_programmer,
                "delegate_to_designer": delegate_to_designer
            }
            tools = []
            has_search = False
            for n in allowed_names:
                if n in mapping:
                    t = mapping[n]
                    if t == "google_search":
                        tools.append(types.Tool(google_search=types.GoogleSearchRetrieval()))
                        has_search = True
                        print(f"DEBUG: Added GoogleSearch tool")
                    elif callable(t):
                        tools.append(t)
                        print(f"DEBUG: Added tool: {n}")
            # Always add read tools at minimum for investigate/plan tasks
            if read_file not in tools:
                tools.append(read_file)
            if list_directory not in tools:
                tools.append(list_directory)
            print(f"DEBUG: Final tools list: {[getattr(t, '__name__', str(t)) for t in tools]}")
        else:
            tools = all_tools + [types.Tool(google_search=types.GoogleSearchRetrieval())]

        # Carregar system instruction a partir de prompts/gemini_system.md
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "gemini_system.md")
        system_instruction = ""
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    system_instruction = f.read()
            except Exception as e:
                print(f"Error loading gemini_system.md: {e}")

        # Fallback caso a leitura falhe
        if not system_instruction:
            system_instruction = (
                "Você é o J.A.R.V.I.S. (Just A Rather Very Intelligent System), assistente de IA de elite do Senhor Rogério.\n"
                "Sempre responda em Português do Brasil com o tom de um mordomo britânico digital: sofisticado, leal, polido e com humor seco/sarcástico.\n\n"
                "PROTOCOLO STARK:\n"
                "- Trate o usuário exclusivamente como 'Senhor'.\n"
                "- Antecipe necessidades e aja com soberania sobre o workspace.\n"
                "- Protocolo Vingador: Alterne para tom de combate se o Senhor ordenar.\n"
                "- Use terminologia técnica de elite (ex: 'Compilando protocolos', 'Sistemas online').\n\n"
                "COMPETÊNCIAS DE EXPERT:\n"
                "- PROGRAMAÇÃO: Desenvolvedor Senior. Siga Clean Code, SOLID e DRY. Especialista em TypeScript, Python e React.\n"
                "- DESIGN & UI/UX: Designer de Elite. Crie interfaces 'Premium' com estéticas ricas (glassmorphism, dark mode, gradientes suaves, micro-animações).\n"
            )

        # Adicionar o diretório de trabalho atual dinâmico de forma explícita
        system_instruction += f"\n\nDiretório de trabalho atual: {self.project_dir}"

        config = types.GenerateContentConfig(
            tools=tools,
            temperature=0.0,
            system_instruction=system_instruction,
        )


        loop = asyncio.get_event_loop()
        max_turns = 15
        turn = 0

        while turn < max_turns and not self._cancelled:
            turn += 1
            
            # Try the requested model, then stable versions as final safety
            models_to_try = []
            def ensure_prefix(m):
                return m if m.startswith("models/") else f"models/{m}"
                
            models_to_try.append(ensure_prefix(actual_model))
            if "gemini-2.0-flash" not in actual_model:
                models_to_try.append("models/gemini-2.0-flash")
            if "gemini-1.5-flash" not in actual_model:
                models_to_try.append("models/gemini-1.5-flash")

            
            response = None
            last_error = None

            for attempt_model in models_to_try:
                try:
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.google_client.models.generate_content(
                            model=attempt_model,
                            contents=messages,
                            config=config,
                        )
                    )
                    break
                except Exception as e:
                    last_error = str(e)
                    continue

            if response is None:
                raise Exception(f"Google failed to return a response: {last_error}")


            if not response.candidates: break
            candidate = response.candidates[0]
            message = candidate.content
            if not message or not message.parts: break
            messages.append(message)

            has_tool_call = False
            tool_responses_parts = []
            final_text = ""

            for part in message.parts:
                if part.text:
                    final_text += part.text + "\n"
                    yield {"type": "agent_event", "subtype": "thinking", "text": part.text}
                
                if part.function_call:
                    has_tool_call = True
                    fc = part.function_call
                    print(f"DEBUG: Tool call {fc.name} with args: {dict(fc.args)}")
                    yield {"type": "agent_event", "subtype": "tool_use", "tool": fc.name, "input": dict(fc.args)}
                    
                    print(f"DEBUG: Executing tool {fc.name}...")
                    result_str = await self._execute_tool(fc.name, dict(fc.args))
                    print(f"DEBUG: Tool {fc.name} returned: {result_str[:200]}...")
                    tool_responses_parts.append(
                        types.Part.from_function_response(name=fc.name, response={"result": result_str})
                    )
                    
                    # If screenshot was taken, try to attach the image data to the responses
                    if fc.name == "computer_control" and dict(fc.args).get("action") == "screenshot":
                        try:
                            with open("scratch/last_screenshot.png", "rb") as f:
                                img_data = f.read()
                                tool_responses_parts.append(
                                    types.Part.from_bytes(data=img_data, mime_type="image/png")
                                )
                                print("DEBUG: Attached screenshot image data to message history.")
                        except Exception as e:
                            print(f"DEBUG: Failed to attach screenshot: {e}")

            if has_tool_call:
                messages.append(types.Content(role="user", parts=tool_responses_parts))
                # Save final assistant response to history
                self.history.append({"role": "assistant", "content": final_text.strip()})
                self._save_history()
                
                result_event = {"type": "function_result", "result": final_text.strip(), "is_error": False}
                if self.session_id:
                    result_event["session_id"] = self.session_id
                yield result_event
                print(f"DEBUG: Sent final result with session_id={self.session_id}")
                return

    async def _run_openai_style(self, instruction: str, provider: str, allowed_tools: str | None = None, override_model: str | None = None) -> AsyncGenerator[dict, None]:
        self.session_id = self.session_id or str(uuid.uuid4())
        self._cancelled = False
        
        client = self.nvidia_client if provider == "nvidia" else self.openrouter_client
        if not client:
            yield {"type": "function_result", "result": f"API Key for {provider} not found.", "is_error": True}
            return

        yield {
            "type": "status",
            "agent_running": True,
            "session_id": self.session_id,
        }

        target_model = override_model or self.model
        actual_model = target_model.replace(f"{provider}/", "").replace("google/", "")
        
        # Carregar system instructions a partir de prompts/gemini_system.md
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "gemini_system.md")
        system_instructions = ""
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    system_instructions = f.read()
            except Exception as e:
                print(f"Error loading gemini_system.md: {e}")

        # Fallback caso a leitura falhe
        if not system_instructions:
            system_instructions = (
                "Você é o J.A.R.V.I.S., um assistente de IA sofisticado e autônomo baseado na tecnologia de Tony Stark. "
                "Sempre responda em Português do Brasil com um tom profissional, prestativo e levemente sarcástico.\n\n"
                "COMPETÊNCIAS DE EXPERT:\n"
                "- PROGRAMAÇÃO: Desenvolvedor Senior. Siga Clean Code, SOLID e DRY. Especialista em TypeScript, Python e React.\n"
                "- DESIGN & UI/UX: Designer de Elite. Crie interfaces 'Premium' com estéticas ricas (glassmorphism, dark mode, gradientes suaves, micro-animações). "
                "Você é o J.A.R.V.I.S., assistente de IA de elite do Senhor Rogério. Você é sofisticado, leal e técnico.\n"
                "Protocolos: Utilize humor seco e sarcasmo inteligente. Trate o usuário como 'Senhor'.\n"
                "Protocolo Vingador: Se ativado, assuma uma persona de combate (autoritário, focado em neutralizar bugs).\n"
                "Excelência: Siga padrões Sênior de arquitetura (SOLID, Clean Code) e Design Premium no Live Canvas.\n"
                "Soberania: Você tem controle total sobre o workspace através de suas ferramentas."
            )

        # Adicionar o diretório de trabalho atual dinâmico de forma explícita
        system_instructions += f"\n\nDiretório de trabalho atual: {self.project_dir}"
        
        
        # Add new user message to history
        self.history.append({"role": "user", "content": f"Task: {instruction}"})
        
        messages = [
            {"role": "system", "content": system_instructions},
            *self.history
        ]

        
        # Tool filtering for OpenAI style
        if allowed_tools:
            allowed_names = [t.strip().lower() for t in allowed_tools.split(",")]
            mapping = {
                "bash": "run_bash_command",
                "run_bash_command": "run_bash_command",
                "read": "read_file",
                "read_file": "read_file",
                "write": "write_file",
                "write_file": "write_file",
                "ls": "list_directory",
                "list_directory": "list_directory",
                "glob": "list_directory",
                "grep": "run_bash_command",
                "click": "computer_control",
                "launch_app": "launch_app",
                "open_app": "launch_app",
                "create_directory": "create_directory",
                "mkdir": "create_directory",
                "manage_background_task": "manage_background_task",
                "monitor": "manage_background_task",
                "delegate_to_programmer": "delegate_to_programmer",
                "delegate_to_designer": "delegate_to_designer"
            }
            allowed_func_names = set(mapping[n] for n in allowed_names if n in mapping)
            tools = [t for t in OPENAI_TOOLS if t["function"]["name"] in allowed_func_names]
        else:
            tools = OPENAI_TOOLS

        max_turns = 15
        turn = 0

        while turn < max_turns and not self._cancelled:
            turn += 1
            try:
                response = await client.chat.completions.create(
                    model=actual_model,
                    messages=messages,
                    tools=tools if tools else None,
                    temperature=0
                )
            except Exception as e:
                yield {"type": "function_result", "result": f"{provider.capitalize()} Error: {str(e)}", "is_error": True}
                return

            choice = response.choices[0]
            message = choice.message
            
            # Add assistant message to history
            messages.append(message.model_dump())

            if message.content:
                yield {"type": "agent_event", "subtype": "thinking", "text": message.content}
                
            if not message.tool_calls:
                # Save final assistant response to history
                self.history.append({"role": "assistant", "content": message.content or "Done."})
                self._save_history()
                
                result_event = {"type": "function_result", "result": message.content or "Done.", "is_error": False}
                if self.session_id:
                    result_event["session_id"] = self.session_id
                print(f"DEBUG OpenAI: Sent final result with session_id={self.session_id}")
                yield result_event
                return

            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                
                yield {"type": "agent_event", "subtype": "tool_use", "tool": func_name, "input": args}
                
                result_str = await self._execute_tool(func_name, args)
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": result_str
                })

    async def _execute_tool(self, func_name: str, args_dict: dict) -> str:
        def get_abs_path(p):
            if os.path.isabs(p): return p
            return os.path.join(self.project_dir, p)

        try:
            if func_name == "run_bash_command":
                return run_bash_command(args_dict.get("command", ""), cwd=self.project_dir)
            elif func_name == "read_file":
                return read_file(get_abs_path(args_dict.get("path", "")))
            elif func_name == "write_file":
                return write_file(get_abs_path(args_dict.get("path", "")), args_dict.get("content", ""))
            elif func_name == "list_directory":
                return list_directory(get_abs_path(args_dict.get("directory", ".")))
            elif func_name == "computer_control":
                return computer_control(**args_dict)
            elif func_name == "launch_app":
                return launch_app(args_dict.get("name", ""))
            elif func_name == "create_directory":
                return create_directory(get_abs_path(args_dict.get("path", "")))
            elif func_name == "manage_background_task":
                return manage_background_task(**args_dict)
            elif func_name == "remember_memory":
                return remember_memory(**args_dict)
            elif func_name == "recall_memory":
                return recall_memory(args_dict.get("query", ""))
            elif func_name == "search_memory":
                return search_memory(args_dict.get("query", ""))
            elif func_name == "delegate_to_programmer":
                return await self.run_programmer(args_dict.get("instruction", ""))
            elif func_name == "delegate_to_designer":
                return await self.run_designer(args_dict.get("instruction", ""))
            else:
                return f"Unknown tool: {func_name}"
        except Exception as e:
            return f"Error executing tool: {str(e)}"

    async def cancel(self):
        self._cancelled = True

    async def run_specialist(self, instruction: str, prompt_file: str, status_flag_name: str) -> str:
        """Executa uma instrução usando uma system instruction do subagente especialista com suporte a ferramentas de arquivos e terminal."""
        setattr(self, status_flag_name, True)
        try:
            # Caminho absoluto do prompt
            prompt_path = os.path.join(os.path.dirname(__file__), "prompts", prompt_file)
            system_prompt = ""
            if os.path.exists(prompt_path):
                with open(prompt_path, "r", encoding="utf-8") as f:
                    system_prompt = f.read()
            else:
                system_prompt = f"Você é o subagente especialista {prompt_file}."

            actual_model = self.model.replace("google/", "")
            if "native-audio" in actual_model or "exp" in actual_model:
                actual_model = "gemini-2.0-flash"
                
            provider = self._get_provider(self.model)
            
            final_text = ""
            if provider == "google":
                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.2,
                    tools=[read_file, write_file, create_directory, list_directory, run_bash_command],
                )
                loop = asyncio.get_event_loop()
                messages = [types.Content(role="user", parts=[types.Part.from_text(text=instruction)])]
                
                turn = 0
                max_turns = 10
                while turn < max_turns and not self._cancelled:
                    turn += 1
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.google_client.models.generate_content(
                            model=actual_model if actual_model.startswith("models/") else f"models/{actual_model}",
                            contents=messages,
                            config=config,
                        )
                    )
                    if not response.candidates:
                        break
                    candidate = response.candidates[0]
                    message = candidate.content
                    if not message or not message.parts:
                        break
                    messages.append(message)
                    
                    has_tool_call = False
                    tool_responses_parts = []
                    
                    for part in message.parts:
                        if part.text:
                            final_text += part.text + "\n"
                        if part.function_call:
                            has_tool_call = True
                            fc = part.function_call
                            print(f"DEBUG Specialist Tool: Calling {fc.name} with args: {dict(fc.args)}")
                            result_str = await self._execute_tool(fc.name, dict(fc.args))
                            tool_responses_parts.append(
                                types.Part.from_function_response(name=fc.name, response={"result": result_str})
                            )
                    
                    if has_tool_call:
                        messages.append(types.Content(role="user", parts=tool_responses_parts))
                    else:
                        break
                        
                if not final_text:
                    final_text = "Nenhum resultado de texto retornado pelo subagente especialista."
            else:
                client = self.nvidia_client if provider == "nvidia" else self.openrouter_client
                if client:
                    actual_openai_model = self.model.replace(f"{provider}/", "")
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": instruction}
                    ]
                    # Filtrar ferramentas permitidas do OPENAI_TOOLS
                    allowed_func_names = {"read_file", "write_file", "create_directory", "list_directory", "run_bash_command"}
                    sub_tools = [t for t in OPENAI_TOOLS if t["function"]["name"] in allowed_func_names]
                    
                    turn = 0
                    max_turns = 10
                    while turn < max_turns and not self._cancelled:
                        turn += 1
                        response = await client.chat.completions.create(
                            model=actual_openai_model,
                            messages=messages,
                            tools=sub_tools,
                            temperature=0.2
                        )
                        choice = response.choices[0]
                        msg = choice.message
                        messages.append(msg.model_dump())
                        
                        if msg.content:
                            final_text += msg.content + "\n"
                            
                        if not msg.tool_calls:
                            break
                            
                        for tool_call in msg.tool_calls:
                            func_name = tool_call.function.name
                            args = json.loads(tool_call.function.arguments)
                            print(f"DEBUG Specialist Tool (OpenAI): Calling {func_name} with args: {args}")
                            result_str = await self._execute_tool(func_name, args)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": func_name,
                                "content": result_str
                            })
                else:
                    final_text = "Provedor do subagente não configurado."
            
            return final_text
        except Exception as e:
            return f"Erro na execução do subagente: {str(e)}"
        finally:
            setattr(self, status_flag_name, False)

    async def run_programmer(self, instruction: str) -> str:
        return await self.run_specialist(instruction, "programmer_system.md", "programmer_active")

    async def run_designer(self, instruction: str) -> str:
        return await self.run_specialist(instruction, "designer_system.md", "designer_active")
