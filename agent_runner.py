import asyncio
import json
import os
import subprocess
import time
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

# Roteamento de modelos
from model_router import ModelRouter, AllModelsFailed

def _shell_env() -> dict:
    """PATH com o Python que roda o servidor na frente, para 'python'/'pip' funcionarem
    mesmo quando o PATH do sistema só tem o atalho da Microsoft Store."""
    import sys
    env = os.environ.copy()
    base_python = getattr(sys, "_base_executable", sys.executable)
    base_dir = os.path.dirname(base_python)
    extra = [base_dir, os.path.join(base_dir, "Scripts")]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env

def run_bash_command(command: str, cwd: str = None) -> str:
    """Runs a bash/shell command and returns its stdout and stderr."""
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120, cwd=cwd,
                             env=_shell_env(), encoding="utf-8", errors="replace")
        return f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}\nEXIT_CODE: {res.returncode}"
    except Exception as e:
        return f"Error: {str(e)}"

READ_FILE_MAX_LINES = 2000

def read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    """Reads the contents of a file. For big files, pass offset (first line, 0-based) and limit (number of lines) to read only a slice."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        offset = int(offset or 0)
        limit = int(limit or 0)
        if offset == 0 and limit == 0 and text.count("\n") < READ_FILE_MAX_LINES:
            return text
        lines = text.splitlines(keepends=True)
        end = offset + (limit or READ_FILE_MAX_LINES)
        chunk = "".join(lines[offset:end])
        if end < len(lines):
            chunk += f"\n[... arquivo com {len(lines)} linhas; mostradas {offset}-{end}. Use offset/limit para ler o resto.]"
        return chunk
    except Exception as e:
        return f"Error: {str(e)}"

def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Edits a file by replacing an exact snippet (old_string) with new_string. Much faster than rewriting the whole file with write_file. old_string must match the file exactly (including indentation) and be unique unless replace_all is true."""
    try:
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8")
        if not old_string:
            return "Error: old_string vazio. Para criar arquivo novo use write_file."
        count = text.count(old_string)
        if count == 0:
            return "Error: old_string não encontrado no arquivo. Leia o arquivo de novo e copie o trecho exato."
        if count > 1 and not replace_all:
            return f"Error: old_string aparece {count} vezes. Inclua mais contexto para torná-lo único ou use replace_all=true."
        new_text = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)
        file_path.write_text(new_text, encoding="utf-8")
        return f"Successfully edited {path} ({count if replace_all else 1} substituição(ões))."
    except Exception as e:
        return f"Error: {str(e)}"

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".voicecode", ".next"}

def _walk_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            yield os.path.join(dirpath, name)

def find_files(pattern: str, directory: str = ".") -> str:
    """Finds files by glob pattern (e.g. '*.py', 'src/**/*.tsx') recursively, ignoring node_modules/.git/.venv/dist."""
    import fnmatch
    try:
        results = []
        for full in _walk_files(directory):
            rel = os.path.relpath(full, directory).replace("\\", "/")
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(os.path.basename(full), pattern):
                results.append(rel)
                if len(results) >= 300:
                    results.append("[... limite de 300 resultados]")
                    break
        return "\n".join(results) if results else "(nenhum arquivo encontrado)"
    except Exception as e:
        return f"Error: {str(e)}"

def search_code(pattern: str, directory: str = ".", file_glob: str = "") -> str:
    """Searches file contents with a regex (like grep -n). Optional file_glob filters files (e.g. '*.py'). Returns path:line: text."""
    import fnmatch
    import re
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: regex inválida: {e}"
    results = []
    try:
        for full in _walk_files(directory):
            if file_glob and not fnmatch.fnmatch(os.path.basename(full), file_glob):
                continue
            try:
                if os.path.getsize(full) > 2_000_000:
                    continue
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            rel = os.path.relpath(full, directory).replace("\\", "/")
                            results.append(f"{rel}:{i}: {line.rstrip()[:200]}")
                            if len(results) >= 200:
                                return "\n".join(results) + "\n[... limite de 200 resultados]"
            except (OSError, UnicodeDecodeError):
                continue
        return "\n".join(results) if results else "(nenhuma ocorrência)"
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
            "description": "Reads the contents of a file. For big files use offset/limit to read a slice of lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "offset": {"type": "integer", "description": "First line (0-based). Optional."},
                    "limit": {"type": "integer", "description": "Number of lines. Optional."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edits a file replacing an exact snippet (old_string) with new_string. Prefer this over write_file for changes to existing files: it is much faster.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "old_string": {"type": "string", "description": "Exact text to replace (must be unique unless replace_all)."},
                    "new_string": {"type": "string", "description": "Replacement text."},
                    "replace_all": {"type": "boolean", "description": "Replace every occurrence."}
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "Finds files by glob pattern recursively (e.g. '*.py', 'src/**/*.tsx').",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern."},
                    "directory": {"type": "string", "description": "Base directory. Optional."}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Searches file contents with a regex (like grep -n). Returns path:line: text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex to search."},
                    "directory": {"type": "string", "description": "Base directory. Optional."},
                    "file_glob": {"type": "string", "description": "Filter files, e.g. '*.py'. Optional."}
                },
                "required": ["pattern"]
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

# ── Modelos ────────────────────────────────────────────────────
# A escolha do modelo de cada tarefa fica com o ModelRouter (model_router.py).

_router: ModelRouter | None = None

def get_router() -> ModelRouter:
    """Roteador compartilhado: a saúde dos modelos sobrevive à troca de projeto."""
    global _router
    if _router is None:
        _router = ModelRouter({
            "google": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
            "nvidia": bool(os.getenv("NVIDIA_API_KEY")),
            "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
        })
    return _router

# Ferramentas Python cujas assinaturas viram declarações para o Gemini.
# A execução é sempre feita por AgentRunner._execute_tool (caminhos relativos ao projeto).
CODING_TOOLS = [read_file, edit_file, write_file, find_files, search_code, list_directory, create_directory, run_bash_command]
READ_ONLY_TOOLS = {"read_file", "find_files", "search_code", "list_directory", "recall_memory", "search_memory"}

# O prompt compartilhado com a voz cita os nomes de lá (run_command etc.); o agente aceita como apelido
TOOL_ALIASES = {
    "run_command": "run_bash_command", "bash": "run_bash_command", "shell": "run_bash_command",
    "read": "read_file", "write": "write_file", "edit": "edit_file",
    "grep": "search_code", "search": "search_code", "glob": "find_files", "ls": "list_directory",
    "mkdir": "create_directory",
}
KNOWN_TOOLS = {t.__name__ for t in CODING_TOOLS} | {
    "computer_control", "launch_app", "manage_background_task", "remember_memory",
    "recall_memory", "search_memory", "delegate_to_programmer", "delegate_to_designer",
}

# Chamada por modelo: falha rápido para trocar de modelo em vez de esperar retentativas do SDK
GOOGLE_HTTP_OPTIONS = types.HttpOptions(timeout=90_000, retry_options=types.HttpRetryOptions(attempts=1))
OPENAI_TIMEOUT = 90

def google_tool_config(**kwargs) -> types.GenerateContentConfig:
    """Config com chamada automática do SDK desligada: nós executamos as ferramentas."""
    return types.GenerateContentConfig(
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        **kwargs,
    )

class AgentRunner:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.session_id = None
        self.model = "auto"   # "auto" = roteamento por tipo de tarefa; ou id do catálogo para fixar
        self.effort = "high"
        self._cancelled = False
        self.router = get_router()

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
            # Fallback: use project-local brain directory
            local_brain = os.path.join(self.project_dir, ".voicecode", "brain")
            os.makedirs(local_brain, exist_ok=True)
            self.obsidian = ObsidianBridge(local_brain)
            set_obsidian_instance(self.obsidian)
            print(f"Obsidian vault (local fallback): {local_brain}")

        # Clients
        self.google_client = genai.Client(http_options=GOOGLE_HTTP_OPTIONS) if self.router.providers.get("google") else None
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        self.nvidia_client = AsyncOpenAI(
            api_key=nvidia_key, base_url="https://integrate.api.nvidia.com/v1",
            timeout=OPENAI_TIMEOUT, max_retries=0,
        ) if nvidia_key else None
        or_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_client = AsyncOpenAI(
            api_key=or_key, base_url="https://openrouter.ai/api/v1",
            timeout=OPENAI_TIMEOUT, max_retries=0,
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
        if not model_id or model_id == "auto":
            return "auto"
        spec = self.router.get(model_id)
        return spec.provider if spec else "google"

    def _client_for(self, provider: str):
        return {"nvidia": self.nvidia_client, "openrouter": self.openrouter_client}.get(provider)

    # ── Execução de uma tarefa com roteamento de modelos ───────

    async def run(
        self,
        instruction: str,
        mode: str = "edit",
        allowed_tools: str | None = None,
        permission_mode: str | None = None,
        task_kind: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        self.session_id = self.session_id or str(uuid.uuid4())
        self._cancelled = False
        yield {"type": "status", "agent_running": True, "session_id": self.session_id}

        system_prompt = self._load_system_prompt(fallback=(
            "Você é o J.A.R.V.I.S., assistente de IA de elite do Senhor Rogério. "
            "Sempre responda em Português do Brasil. Siga padrões Sênior (SOLID, Clean Code)."
        ))
        user_text = f"Task: {instruction}"
        prior = list(self.history)

        final_text = ""
        is_error = False
        try:
            async for event in self._execute_plan(
                task_kind=task_kind or "code_task",
                system_prompt=system_prompt,
                user_text=user_text,
                prior=prior,
                google_tools=self._google_tools(allowed_tools),
                temperature=0.0,
                max_turns=30,
            ):
                if event["type"] == "_final":
                    final_text = event["text"]
                else:
                    yield event
        except Exception as e:
            final_text = f"Erro: {e}"
            is_error = True

        final_text = final_text or "Done."
        if not is_error:
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": final_text})
            self._save_history()

        result_event = {"type": "function_result", "result": final_text, "is_error": is_error}
        if self.session_id:
            result_event["session_id"] = self.session_id
        yield result_event

    async def _execute_plan(self, task_kind: str, system_prompt: str, user_text: str, prior: list,
                            google_tools: list, temperature: float, max_turns: int) -> AsyncGenerator[dict, None]:
        """Pede ao roteador a lista de modelos e executa no primeiro provedor que responder.
        Dentro de um provedor, cada turno troca de modelo se o atual falhar."""
        tier, plan = self.router.plan(task_kind, pinned=self.model, effort=self.effort)
        if not plan:
            raise AllModelsFailed("Nenhum modelo disponível. Verifique as chaves de API no .env.")

        # Blocos contíguos por provedor, preservando a ordem do plano: dentro do mesmo
        # nível troca-se de provedor antes de descer para um modelo de nível inferior.
        groups: list[tuple[str, list]] = []
        for spec in plan:
            if groups and groups[-1][0] == spec.provider:
                groups[-1][1].append(spec)
            else:
                groups.append((spec.provider, [spec]))

        yield {"type": "agent_event", "subtype": "route", "tier": tier, "task": task_kind,
               "candidates": [s.id for s in plan[:4]]}

        allowed_names = {getattr(t, "__name__", "") for t in google_tools}
        openai_tools = [t for t in OPENAI_TOOLS if t["function"]["name"] in allowed_names]

        last_error = None
        for attempt, (provider, specs) in enumerate(groups):
            text = user_text
            if attempt > 0:
                text += ("\n\n(Observação: uma tentativa anterior com outro provedor foi interrompida; "
                         "confira o estado atual dos arquivos antes de alterar.)")
            try:
                if provider == "google":
                    if not self.google_client:
                        continue
                    messages = [types.Content(role="user" if m["role"] == "user" else "model",
                                              parts=[types.Part.from_text(text=m["content"])]) for m in prior]
                    messages.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
                    config = google_tool_config(tools=google_tools, temperature=temperature, system_instruction=system_prompt)
                    loop = self._google_loop(messages, config, specs, tier, task_kind, max_turns)
                else:
                    client = self._client_for(provider)
                    if not client:
                        continue
                    messages = [{"role": "system", "content": system_prompt}, *prior, {"role": "user", "content": text}]
                    loop = self._openai_loop(client, messages, openai_tools, specs, tier, task_kind, temperature, max_turns)
                async for event in loop:
                    yield event
                return
            except AllModelsFailed as e:
                last_error = e
                yield {"type": "agent_event", "subtype": "thinking",
                       "text": f"⚠️ Nenhum modelo {provider} respondeu ({e}). Tentando outro provedor..."}
        raise AllModelsFailed(f"Todos os modelos falharam. Último erro: {last_error}")

    async def _call_with_fallback(self, specs: list, call, tier: str, task_kind: str, state: dict):
        """Tenta cada modelo da lista (pulando os em espera). state['current'] guarda o que respondeu."""
        errors = []
        ordered = sorted(specs, key=lambda s: 0 if s.id == state.get("current") else 1)
        # Pula os que estão em espera; se todos estiverem, tenta assim mesmo
        ordered = [s for s in ordered if self.router.is_available(s.id)] or ordered
        for spec in ordered:
            t0 = time.time()
            try:
                response = await call(spec.model)
            except Exception as e:
                reason = self.router.report_failure(spec.id, str(e))
                errors.append(f"{spec.label}: {reason}")
                print(f"DEBUG: modelo {spec.id} falhou ({reason}): {str(e)[:150]}")
                continue
            self.router.report_success(spec.id, time.time() - t0, tier, task_kind)
            switched = state.get("current") != spec.id
            state["current"] = spec.id
            return response, spec, switched
        raise AllModelsFailed("; ".join(errors) or "todos em espera")

    # ── Prompt e ferramentas ───────────────────────────────────

    def _load_system_prompt(self, prompt_file: str = "gemini_system.md", fallback: str = "") -> str:
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", prompt_file)
        text = ""
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                print(f"Error loading {prompt_file}: {e}")
        return (text or fallback) + self._coding_guidelines()

    def _coding_guidelines(self) -> str:
        shell = "cmd.exe (Windows) — use comandos Windows ou 'powershell -Command ...'" if os.name == "nt" else "sh"
        return (
            "\n\n## Ambiente e eficiência de codificação\n"
            f"- Diretório de trabalho atual: {self.project_dir}. Caminhos relativos são resolvidos a partir dele.\n"
            f"- run_bash_command executa em {shell}.\n"
            "- Para alterar arquivos existentes use edit_file (substitui só o trecho), não reescreva o arquivo inteiro com write_file. "
            "write_file só para arquivos novos ou reescritas completas.\n"
            "- Antes de editar, leia o trecho com read_file e copie o old_string exatamente como está.\n"
            "- Para localizar código use search_code (regex) e find_files (glob), em vez de comandos de shell.\n"
            "- 'python' e 'pip' já estão no PATH do shell. Não varra o disco inteiro (ex.: find_files em C:/); trabalhe dentro do projeto.\n"
            "- Quando precisar de várias leituras/buscas independentes, peça todas na MESMA resposta: elas rodam em paralelo.\n"
            "- Depois de alterar código, valide (build, testes ou execução) com run_bash_command quando houver como.\n"
        )

    def _google_tools(self, allowed_tools: str | None) -> list:
        if not allowed_tools:
            return CODING_TOOLS + [computer_control, launch_app, manage_background_task,
                                   remember_memory, recall_memory, search_memory,
                                   delegate_to_programmer, delegate_to_designer]
        mapping = {
            "bash": run_bash_command, "run_bash_command": run_bash_command,
            "read": read_file, "read_file": read_file,
            "edit": edit_file, "edit_file": edit_file,
            "write": write_file, "write_file": write_file,
            "ls": list_directory, "list_directory": list_directory,
            "glob": find_files, "find_files": find_files,
            "grep": search_code, "search_code": search_code, "search": search_code,
            "computer_control": computer_control, "computer_use": computer_control,
            "screenshot": computer_control, "mouse": computer_control, "click": computer_control,
            "launch_app": launch_app, "open_app": launch_app, "open_url": launch_app,
            "background_task": manage_background_task, "monitor": manage_background_task,
            "manage_background_task": manage_background_task,
            "create_directory": create_directory, "mkdir": create_directory,
            "delegate_to_programmer": delegate_to_programmer,
            "delegate_to_designer": delegate_to_designer,
        }
        tools = []
        for n in (t.strip().lower() for t in allowed_tools.split(",")):
            t = mapping.get(n)
            if t and t not in tools:
                tools.append(t)
        # Ferramentas de leitura sempre disponíveis para investigar/planejar
        for t in (read_file, list_directory, find_files, search_code):
            if t not in tools:
                tools.append(t)
        return tools

    # ── Laço Gemini ────────────────────────────────────────────

    async def _google_loop(self, messages: list, config, specs: list, tier: str, task_kind: str,
                           max_turns: int = 30) -> AsyncGenerator[dict, None]:
        """Ciclo modelo → ferramentas → modelo até não haver mais chamadas.
        Emite eventos e, por último, {"type": "_final", "text": ...}."""
        state: dict = {}
        last_text = ""
        all_text = ""

        for _ in range(max_turns):
            if self._cancelled:
                break

            async def call(model_name):
                return await self.google_client.aio.models.generate_content(
                    model=model_name, contents=messages, config=config,
                )
            response, spec, switched = await self._call_with_fallback(specs, call, tier, task_kind, state)
            if switched:
                yield {"type": "agent_event", "subtype": "model", "model": spec.id, "label": spec.label, "tier": tier}

            if not response.candidates:
                break
            message = response.candidates[0].content
            if not message or not message.parts:
                break
            messages.append(message)

            calls = []
            turn_text = ""
            for part in message.parts:
                if part.text and not getattr(part, "thought", False):
                    turn_text += part.text + "\n"
                    yield {"type": "agent_event", "subtype": "thinking", "text": part.text}
                if part.function_call:
                    calls.append(part.function_call)
            if turn_text.strip():
                last_text = turn_text
                all_text += turn_text

            if not calls:
                break

            named = [(fc.name, dict(fc.args or {})) for fc in calls]
            for name, args in named:
                yield {"type": "agent_event", "subtype": "tool_use", "tool": name, "input": args}
            results = await self._execute_tool_calls(named)

            parts = []
            for (name, args), result_str in zip(named, results):
                parts.append(types.Part.from_function_response(name=name, response={"result": result_str}))
                if name == "computer_control" and args.get("action") == "screenshot":
                    try:
                        with open("scratch/last_screenshot.png", "rb") as f:
                            parts.append(types.Part.from_bytes(data=f.read(), mime_type="image/png"))
                    except Exception as e:
                        print(f"DEBUG: Failed to attach screenshot: {e}")
            messages.append(types.Content(role="user", parts=parts))
        else:
            all_text += f"\n[Limite de {max_turns} turnos atingido.]"
            last_text = all_text

        yield {"type": "_final", "text": (last_text or all_text).strip()}

    # ── Laço OpenAI (NVIDIA / OpenRouter) ──────────────────────

    async def _openai_loop(self, client, messages: list, tools: list, specs: list, tier: str, task_kind: str,
                           temperature: float, max_turns: int = 30) -> AsyncGenerator[dict, None]:
        state: dict = {}
        last_text = ""
        for _ in range(max_turns):
            if self._cancelled:
                break

            async def call(model_name):
                return await client.chat.completions.create(
                    model=model_name, messages=messages, tools=tools or None, temperature=temperature,
                )
            response, spec, switched = await self._call_with_fallback(specs, call, tier, task_kind, state)
            if switched:
                yield {"type": "agent_event", "subtype": "model", "model": spec.id, "label": spec.label, "tier": tier}

            message = response.choices[0].message
            messages.append(message.model_dump(exclude_none=True))

            if message.content:
                last_text = message.content
                yield {"type": "agent_event", "subtype": "thinking", "text": message.content}
            if not message.tool_calls:
                break

            named = []
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"__invalid_json__": tc.function.arguments}
                named.append((tc.function.name, args))
                yield {"type": "agent_event", "subtype": "tool_use", "tool": tc.function.name, "input": args}

            results = await self._execute_tool_calls(named)
            for tc, (name, _), result_str in zip(message.tool_calls, named, results):
                messages.append({"role": "tool", "tool_call_id": tc.id, "name": name, "content": result_str})
        else:
            last_text += f"\n[Limite de {max_turns} turnos atingido.]"

        yield {"type": "_final", "text": last_text.strip()}

    # ── Execução de ferramentas ────────────────────────────────

    async def _execute_tool_calls(self, calls: list[tuple[str, dict]]) -> list[str]:
        """Executa as chamadas de um turno. Se todas forem somente leitura, roda em paralelo;
        caso contrário roda em ordem, para que escritas não se atropelem."""
        if len(calls) > 1 and all(TOOL_ALIASES.get(name, name) in READ_ONLY_TOOLS for name, _ in calls):
            return list(await asyncio.gather(*(self._execute_tool(n, a) for n, a in calls)))
        return [await self._execute_tool(n, a) for n, a in calls]

    async def _execute_tool(self, func_name: str, args_dict: dict) -> str:
        def get_abs_path(p):
            p = p or "."
            if os.path.isabs(p):
                return p
            return os.path.join(self.project_dir, p)

        a = args_dict
        func_name = TOOL_ALIASES.get(func_name, func_name)
        try:
            if "__invalid_json__" in a:
                return f"Error: argumentos JSON inválidos: {a['__invalid_json__'][:200]}"
            if func_name == "run_bash_command":
                return await asyncio.to_thread(run_bash_command, a.get("command", ""), self.project_dir)
            elif func_name == "read_file":
                return await asyncio.to_thread(read_file, get_abs_path(a.get("path", "")), a.get("offset", 0), a.get("limit", 0))
            elif func_name == "edit_file":
                return await asyncio.to_thread(edit_file, get_abs_path(a.get("path", "")), a.get("old_string", ""), a.get("new_string", ""), bool(a.get("replace_all", False)))
            elif func_name == "write_file":
                return await asyncio.to_thread(write_file, get_abs_path(a.get("path", "")), a.get("content", ""))
            elif func_name == "find_files":
                return await asyncio.to_thread(find_files, a.get("pattern", "*"), get_abs_path(a.get("directory", ".")))
            elif func_name == "search_code":
                return await asyncio.to_thread(search_code, a.get("pattern", ""), get_abs_path(a.get("directory", ".")), a.get("file_glob", ""))
            elif func_name == "list_directory":
                return await asyncio.to_thread(list_directory, get_abs_path(a.get("directory", ".")))
            elif func_name == "create_directory":
                return await asyncio.to_thread(create_directory, get_abs_path(a.get("path", "")))
            elif func_name == "computer_control":
                return await asyncio.to_thread(computer_control, **a)
            elif func_name == "launch_app":
                return launch_app(a.get("name", ""))
            elif func_name == "manage_background_task":
                return manage_background_task(**a)
            elif func_name == "remember_memory":
                return await asyncio.to_thread(remember_memory, **a)
            elif func_name == "recall_memory":
                return await asyncio.to_thread(recall_memory, a.get("query", ""))
            elif func_name == "search_memory":
                return await asyncio.to_thread(search_memory, a.get("query", ""))
            elif func_name == "delegate_to_programmer":
                return await self.run_programmer(a.get("instruction", ""))
            elif func_name == "delegate_to_designer":
                return await self.run_designer(a.get("instruction", ""))
            else:
                return (f"Erro: a ferramenta '{func_name}' não existe. "
                        f"Use uma destas: {', '.join(sorted(KNOWN_TOOLS))}.")
        except Exception as e:
            return f"Error executing tool: {str(e)}"

    async def cancel(self):
        self._cancelled = True

    # ── Subagentes especialistas ───────────────────────────────

    async def run_specialist(self, instruction: str, prompt_file: str, status_flag_name: str, task_kind: str) -> str:
        """Executa uma instrução com a system instruction do subagente especialista e ferramentas de arquivo/terminal."""
        setattr(self, status_flag_name, True)
        try:
            system_prompt = self._load_system_prompt(prompt_file, fallback=f"Você é o subagente especialista {prompt_file}.")
            final_text = ""
            async for event in self._execute_plan(
                task_kind=task_kind,
                system_prompt=system_prompt,
                user_text=instruction,
                prior=[],
                google_tools=CODING_TOOLS,
                temperature=0.2,
                max_turns=40,
            ):
                if event["type"] == "_final":
                    final_text = event["text"]
            return final_text or "Nenhum resultado de texto retornado pelo subagente especialista."
        except Exception as e:
            return f"Erro na execução do subagente: {str(e)}"
        finally:
            setattr(self, status_flag_name, False)

    async def run_programmer(self, instruction: str) -> str:
        return await self.run_specialist(instruction, "programmer_system.md", "programmer_active", "delegate_to_programmer")

    async def run_designer(self, instruction: str) -> str:
        return await self.run_specialist(instruction, "designer_system.md", "designer_active", "delegate_to_designer")
