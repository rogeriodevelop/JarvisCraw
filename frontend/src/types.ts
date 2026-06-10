// ── Gemini Function Declarations ──────────────────────────────
// Using parametersJsonSchema (standard JSON Schema, lowercase types).
// This is the latest recommended format per @google/genai SDK docs.

import type { FunctionDeclaration } from "@google/genai";

export const functionDeclarations: FunctionDeclaration[] = [
  {
    name: "investigate_and_advise",
    description:
      "Read the user's codebase and answer a question about their project. Use this for ANY question about files, project structure, architecture, or code.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        question: {
          type: "string",
          description: "The question to investigate in the codebase",
        },
      },
      required: ["question"],
    },
  },
  {
    name: "code_task",
    description:
      "Write code, add features, fix bugs, or refactor in the user's project. Only call after user confirms.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        instruction: {
          type: "string",
          description: "What to code",
        },
      },
      required: ["instruction"],
    },
  },
  {
    name: "read_file",
    description:
      "Read and summarize a specific file from the user's project.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        path: {
          type: "string",
          description: "File path to read",
        },
      },
      required: ["path"],
    },
  },
  {
    name: "run_command",
    description:
      "Run a shell command in the user's project. Only call after user confirms.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        command: {
          type: "string",
          description: "Shell command to run",
        },
      },
      required: ["command"],
    },
  },
  {
    name: "get_status",
    description:
      "Get current session status: what files changed, Agent state.",
    parametersJsonSchema: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "open_url",
    description:
      "Open a URL in a new browser tab. Use this to show the user a running localhost server, a webpage, or any URL they want to preview.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        url: {
          type: "string",
          description: "The URL to open, e.g. http://localhost:8000",
        },
      },
      required: ["url"],
    },
  },
  {
    name: "plan_task",
    description:
      "Create a detailed plan for a task WITHOUT making any changes. Use when the user says 'plan', 'think about', 'how would you', 'what's the approach for', or wants to analyze before acting. The Agent reads the code and produces a step-by-step plan.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        instruction: {
          type: "string",
          description: "What to plan — e.g. 'add authentication', 'refactor the database layer'",
        },
      },
      required: ["instruction"],
    },
  },
  {
    name: "debug_issue",
    description:
      "Diagnose a bug or error WITHOUT applying fixes. Use when the user says 'debug', 'why is this broken', 'find the bug', 'what's causing this error'. The Agent investigates the codebase, runs tests if needed, and reports the root cause with a recommended fix.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        description: {
          type: "string",
          description: "Description of the issue — error message, unexpected behavior, or symptom",
        },
      },
      required: ["description"],
    },
  },
  {
    name: "review_changes",
    description:
      "Review code changes for bugs, security issues, and quality. Use when the user says 'review', 'check my code', 'does this look right', 'any issues'. The Agent reviews recent git changes and gives actionable feedback.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        scope: {
          type: "string",
          description: "What to review: 'recent' (default — uncommitted + last commit), 'staged', 'all uncommitted', or a specific file path",
        },
      },
    },
  },
  {
    name: "rewind",
    description:
      "Rewind/undo code changes to a previous checkpoint. Call with no parameters to list available checkpoints. Call with a checkpoint hash to restore to that state. Use when the user says 'undo', 'revert', 'go back', 'rewind', or wants to undo recent changes.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        hash: {
          type: "string",
          description: "The checkpoint hash to restore to. Omit to list available checkpoints.",
        },
      },
    },
  },
  {
    name: "set_agent_model",
    description:
      "Change the AI model and/or reasoning effort used for code tasks. Call this when the user asks to switch models, use a different model, change reasoning effort, or wants faster/smarter responses. If the user asks what models or efforts are available, call this with no parameters to get the current config and available options.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        model: {
          type: "string",
          description: "The model to use: e.g., 'gemini-2.0-flash', 'llama-3.3-70b', 'deepseek-v4', 'kimi-v1.5'",
        },
        effort: {
          type: "string",
          description: "Reasoning effort level: 'low', 'medium', 'high', or 'max'",
          enum: ["low", "medium", "high", "max"],
        },
      },
    },
  },
  {
    name: "cancel_task",
    description:
      "Cancel/stop the currently running Agent operation. Use when the user says 'stop', 'cancel', 'nevermind', 'abort', or wants to halt an ongoing code task.",
    parametersJsonSchema: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "generate_image",
    description: "Generate an image using NVIDIA Picasso (Picasso model).",
    parametersJsonSchema: {
      type: "object",
      properties: {
        prompt: { type: "string", description: "Image description" },
        negativePrompt: { type: "string", description: "What to exclude" },
        aspectRatio: {
          type: "string",
          enum: ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9"],
        },
      },
      required: ["prompt"],
    },
  },
  {
    name: "computer_control",
    description:
      "Control mouse and keyboard. Actions: 'screenshot', 'click', 'double_click', 'type', 'press', 'hotkey', 'move'. Parameters: {x, y, text, key, keys}. ALWAYS take a screenshot first.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          description: "Action: screenshot, click, double_click, type, press, hotkey, or move",
        },
        x: { type: "number", description: "X coordinate" },
        y: { type: "number", description: "Y coordinate" },
        text: { type: "string", description: "Text to type" },
        key: { type: "string", description: "Key to press" },
        keys: { type: "array", items: { type: "string" }, description: "Keys for hotkey" },
      },
      required: ["action"],
    },
  },
  {
    name: "launch_app",
    description: "Launch a Windows application (e.g. 'notepad', 'calc', 'chrome').",
    parametersJsonSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Application name or command" },
      },
      required: ["name"],
    },
  },
  {
    name: "manage_background_task",
    description: "Start or stop a background repeating task or monitoring.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        action: { type: "string", enum: ["start", "stop"] },
        instruction: { type: "string", description: "What to check or report" },
        interval: { type: "number", description: "Interval in seconds" },
      },
      required: ["action", "instruction"],
    },
  },
  {
    name: "write_file",
    description: "Create or update a file with specific content. Much safer than run_command for writing files.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Path to the file" },
        content: { type: "string", description: "Content to write" },
      },
      required: ["path", "content"],
    },
  },
  {
    name: "create_directory",
    description: "Create a new directory (and parent directories if needed).",
    parametersJsonSchema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Path to the directory" },
      },
      required: ["path"],
    },
  },
  {
    name: "list_directory",
    description: "List contents of a directory.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Path to list (default is current directory)" },
      },
    },
  },
  {
    name: "remember_memory",
    description:
      "Save a memory or note to the J.A.R.V.I.S. brain (Obsidian vault) for long-term persistent recall. Use to remember decisions, learnings, important context, or anything the user wants to keep. The Senhor may say 'lembre disso', 'anote isso', 'memorize'.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        content: { type: "string", description: "The information to remember (Markdown supported)" },
        category: {
          type: "string",
          description: "Category: 'session', 'project', 'decision', or 'general'",
          enum: ["session", "project", "decision", "general"],
        },
        tags: { type: "string", description: "Comma-separated tags" },
        project: { type: "string", description: "Project name to link" },
      },
      required: ["content"],
    },
  },
  {
    name: "recall_memory",
    description:
      "Search and recall memories from the J.A.R.V.I.S. brain (Obsidian vault). Use when the user asks 'o que decidimos sobre...', 'você lembra de...', 'qual era aquele...'.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query to find relevant memories" },
      },
      required: ["query"],
    },
  },
  {
    name: "search_memory",
    description:
      "Broad search across all memories in the J.A.R.V.I.S. brain. Returns more results. Use for comprehensive lookups.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search term" },
      },
      required: ["query"],
    },
  },
  {
    name: "delegate_to_programmer",
    description:
      "Delega uma instrução de desenvolvimento de software fullstack complexa para o subagente especialista em programação sênior. Retorna a solução robusta e completa gravada em arquivos.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        instruction: {
          type: "string",
          description: "A instrução ou tarefa detalhada de programação para o especialista.",
        },
      },
      required: ["instruction"],
    },
  },
  {
    name: "delegate_to_designer",
    description:
      "Delega uma instrução de criação de interface, design gráfico, estilo visual contemporâneo ou UX para o subagente especialista em design. Retorna a interface ou design completo gravado em arquivos.",
    parametersJsonSchema: {
      type: "object",
      properties: {
        instruction: {
          type: "string",
          description: "A instrução detalhada de criação de design e UX para o especialista.",
        },
      },
      required: ["instruction"],
    },
  },
];

// ── WebSocket Messages (Browser ↔ Backend) ───────────────────

/** Browser → Backend: forward a Gemini function call */
export interface FunctionCallMessage {
  type: "function_call";
  id: string;
  name: string;
  args: Record<string, unknown>;
}

/** Backend → Browser: Agent tool use event */
export interface AgentToolUseEvent {
  type: "agent_event";
  subtype: "tool_use";
  tool: string;
  input: Record<string, unknown>;
  timestamp?: string;
}

/** Backend → Browser: Agent text output */
export interface AgentTextEvent {
  type: "agent_event";
  subtype: "text";
  text: string;
  timestamp?: string;
}

/** Backend → Browser: function execution complete */
export interface FunctionResultMessage {
  type: "function_result";
  id: string;
  name: string;
  result: string;
  is_error?: boolean;
}

/** Backend → Browser: status update */
export interface StatusMessage {
  type: "status";
  agent_running: boolean;
  session_id: string | null;
}

/** Backend → Browser: Agent thinking output */
export interface AgentThinkingEvent {
  type: "agent_event";
  subtype: "thinking";
  text: string;
}

/** Backend → Browser: Request to clear the Live Canvas */
export interface AgentClearCanvasEvent {
  type: "agent_event";
  subtype: "clear_canvas";
}

export type BackendMessage =
  | AgentToolUseEvent
  | AgentTextEvent
  | AgentThinkingEvent
  | AgentClearCanvasEvent
  | FunctionResultMessage
  | StatusMessage;

// ── Config types ─────────────────────────────────────────────

export interface ServerConfig {
  system_prompt: string;
  model: string;
}

export interface TokenResponse {
  token: string;
}

export interface SessionState {
  gemini_handle: string | null;
  agent_session_id: string | null;
}
