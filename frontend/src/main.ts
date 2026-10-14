/**
 * VoiceClaw — Entry point. Glues together all modules.
 *
 * Flow:
 *   1. O servidor já abre um projeto (último usado ou a pasta padrão)
 *   2. A tela de voz aparece direto; trocar de projeto é uma janela no cabeçalho
 *   3. Modelos, voz e microfone ficam no painel de Ajustes
 */

import "./style.css";
import "./debug-log"; // Ctrl+Shift+D to download log
import { log } from "./debug-log";
import { AudioManager } from "./audio-manager";
import { GeminiConnection } from "./gemini-connection";
import { NarrationConnection } from "./narration-connection";
import { BackendConnection } from "./backend-connection";
import { UI } from "./ui";
import { WaveRenderer } from "./wave-renderer";
import { NvidiaApiService } from "./services/nvidia-api";
import type { BackendMessage, AgentToolUseEvent, AgentTextEvent, AgentThinkingEvent, AgentClearCanvasEvent, AgentRouteEvent, AgentModelEvent } from "./types";

const ui = new UI();

let audioManager: AudioManager | null = null;
let waveRenderer: WaveRenderer | null = null;
let gemini: GeminiConnection | null = null;
let narration: NarrationConnection | null = null;
let backend: BackendConnection | null = null;
let nvidiaApi: NvidiaApiService | null = null;
let isConnected = false;
let voiceReady = false;
let currentProject: string | null = null;
let pendingImages: { mimeType: string; data: string }[] = [];

// Avenger Protocol Audio state
let protocolAudio: HTMLAudioElement | null = null;
let fadeTimeout: number | null = null;
let fadeInterval: number | null = null;

function playProtocolMusic(src: string): void {
  if (protocolAudio) {
    protocolAudio.pause();
    protocolAudio = null;
  }
  if (fadeTimeout) {
    clearTimeout(fadeTimeout);
    fadeTimeout = null;
  }
  if (fadeInterval) {
    clearInterval(fadeInterval);
    fadeInterval = null;
  }

  protocolAudio = new Audio(src);
  protocolAudio.volume = 0.4;
  protocolAudio.play().catch(err => log("AUDIO", `Music playback failed: ${err}`));

  // Fade out após 15 segundos
  fadeTimeout = window.setTimeout(() => {
    if (protocolAudio) {
      fadeInterval = window.setInterval(() => {
        if (protocolAudio && protocolAudio.volume > 0.05) {
          protocolAudio.volume = Math.max(0, protocolAudio.volume - 0.05);
        } else {
          if (fadeInterval) {
            clearInterval(fadeInterval);
            fadeInterval = null;
          }
          protocolAudio?.pause();
          protocolAudio = null;
        }
      }, 200);
    }
  }, 15000);
}

function stopProtocolMusic(): void {
  if (fadeTimeout) {
    clearTimeout(fadeTimeout);
    fadeTimeout = null;
  }
  if (fadeInterval) {
    clearInterval(fadeInterval);
    fadeInterval = null;
  }
  if (protocolAudio) {
    fadeInterval = window.setInterval(() => {
      if (protocolAudio && protocolAudio.volume > 0.05) {
        protocolAudio.volume = Math.max(0, protocolAudio.volume - 0.1);
      } else {
        if (fadeInterval) {
          clearInterval(fadeInterval);
          fadeInterval = null;
        }
        protocolAudio?.pause();
        protocolAudio = null;
      }
    }, 100);
  }
}

// ── Project Picker ───────────────────────────────────────────

async function openProject(path: string): Promise<boolean> {
  try {
    const res = await fetch("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    if (data.error) {
      ui.setPickerError(data.error === "Directory not found" ? "Pasta não encontrada" : data.error);
      return false;
    }
    const changed = currentProject !== null && currentProject !== data.path;
    currentProject = data.path;
    ui.showVoiceScreen(data.path);
    if (!voiceReady) {
      await initVoiceUI();
    } else if (changed) {
      // A voz continua conectada; só o agente passa a trabalhar na nova pasta
      ui.addStatus(`Projeto alterado para ${data.path}`);
      gemini?.sendText(`[Sistema] O projeto de trabalho agora é: ${data.path}`);
    }
    return true;
  } catch {
    ui.setPickerError("Falha ao falar com o servidor");
    return false;
  }
}

async function openProjectPicker(): Promise<void> {
  try {
    const res = await fetch("/api/projects/recent");
    const data = await res.json();
    ui.setRecentProjects(data.recent || [], data.current, data.default);
    ui.showProjectPicker();
    await browseDir(data.current || "~");
  } catch {
    ui.showProjectPicker();
    await browseDir("~");
  }
}

async function browseDir(path: string): Promise<void> {
  try {
    const res = await fetch(`/api/projects/browse?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    if (data.error) return;
    ui.renderFolderBrowser(data.current, data.parent, data.dirs);
  } catch {
    // ignore
  }
}

// ── Voice UI Init ────────────────────────────────────────────

async function initVoiceUI(): Promise<void> {
  // Ensure we don't have multiple instances running
  if (gemini || narration || backend) {
    teardownVoiceUI();
  }

  if (!audioManager) {
    audioManager = new AudioManager();
    await audioManager.init();
  }

  // Fetch NVIDIA API key and other configs
  try {
    const configRes = await fetch("/api/config");
    const config = await configRes.json();
    if (config.NVIDIA_API_KEY) {
      nvidiaApi = new NvidiaApiService(config.NVIDIA_API_KEY);
      log("NVIDIA", "NVIDIA API initialized");
    }
  } catch (err) {
    log("NVIDIA", `Failed to load config: ${err}`);
  }

  const canvas = document.getElementById("wave-canvas") as HTMLCanvasElement;
  if (canvas) {
    waveRenderer = new WaveRenderer(canvas, audioManager);
    waveRenderer.start();
  }

  // Track Agent's activity during a function call so we can include
  // a summary in the function response — this lets Gemini narrate what happened.
  let agentActivityLog: string[] = [];

  // Backend WebSocket — always active
  backend = new BackendConnection((msg: BackendMessage) => {
    (window as any).backend = backend;
    switch (msg.type) {
      case "agent_event": {
        const e = msg as AgentToolUseEvent | AgentTextEvent | AgentThinkingEvent | AgentClearCanvasEvent | AgentRouteEvent | AgentModelEvent;
        if (e.subtype === "route") {
          log("ROUTER", `task=${e.task} tier=${e.tier} candidates=${e.candidates.join(",")}`);
          ui.addRoute(e.task, e.tier, e.candidates);
        } else if (e.subtype === "model") {
          log("ROUTER", `model=${e.model}`);
          ui.addModelSwitch(e.label, e.model, e.tier);
        } else if (e.subtype === "tool_use") {
          const detail = (e.input.path as string) || (e.input.file_path as string) || (e.input.command as string) || (e.input.pattern as string) || "";
          log("AGENT", `tool=${e.tool} ${detail ? "target=" + detail : ""}`);
          ui.addActivityEvent(e);
          agentActivityLog.push(`[${e.tool}] ${detail}`);
          narration?.sendEvent(`Agent used ${e.tool}${detail ? ` on ${detail}` : ""}`);
          
          // Incrementar contadores do Dashboard
          ui.incrementTasksCount();
          if (["find_files", "search_code", "recall_memory", "search_memory"].includes(e.tool)) {
            ui.incrementSearchesCount();
          }
        } else if (e.subtype === "thinking") {
          log("AGENT", `thinking: ${e.text.slice(0, 100)}`);
          ui.addAgentThinking(e.text);
          narration?.sendEvent(`Agent is thinking: ${e.text.slice(0, 200)}`);
        } else if (e.subtype === "text") {
          log("AGENT", `text: ${e.text.slice(0, 100)}`);
          ui.addAgentText(e.text);
        } else if (e.subtype === "clear_canvas") {
          ui.clearCanvas();
        }
        break;
      }

      case "function_result": {
        const preview = msg.result.slice(0, 150);
        log("AGENT", `result id=${msg.id} name=${msg.name} error=${msg.is_error || false} | ${preview}`);
        
        // Debug: verify we have id and name
        if (!msg.id || !msg.name) {
          log("AGENT", `WARNING: Missing id or name in function_result!`);
        }

        // Silence narration BEFORE main Gemini speaks
        narration?.silence();

        // Build enriched response: activity log + result
        let enrichedResult = msg.result;
        if (agentActivityLog.length > 0) {
          const activity = agentActivityLog.join(", ");
          enrichedResult = `[Steps taken: ${activity}]\n\n${msg.result}`;
          agentActivityLog = [];
        }

        if (gemini) {
          if (msg.name === "computer_control" && msg.result.startsWith("SCREENSHOT_DATA:")) {
            const parts = msg.result.split("|RES:");
            const b64 = parts[0].replace("SCREENSHOT_DATA:", "");
            const res = parts[1] || "unknown";
            
            log("AGENT", `Detected screenshot data (RES: ${res}). Sending to Gemini as image part.`);
            
            // Send the function response text first (without the huge b64)
            gemini.sendFunctionResponse(msg.id, msg.name, `Screenshot taken successfully. Resolution: ${res}. I am now seeing the screen.`);
            
            // Then send the image in a separate turn to update Gemini's vision
            gemini.sendText("", [{ mimeType: "image/png", data: b64 }]);
          } else {
            gemini.sendFunctionResponse(msg.id, msg.name, enrichedResult);
          }
        }
        ui.addGeminiToolResult(msg.name, msg.result, msg.is_error || false);
        ui.addActivityDone(msg.is_error || false);
        ui.setAgentWorking(false);
        ui.addStatus("Agente terminou");
        break;
      }

      case "status":
        log("AGENT", `status running=${msg.agent_running} session=${msg.session_id}`);
        ui.setAgentWorking(msg.agent_running);
        if (msg.agent_running) {
                    ui.addStatus(`Agente trabalhando (sessão ${msg.session_id?.slice(0, 8) || "nova"})`);
        }
        break;
    }
  }, (connected) => {
        ui.addStatus(connected ? "Servidor conectado" : "Servidor desconectado");
  });
  backend.connect();

  // Connect/Disconnect button
  ui.onConnectClick(async () => {
    // Prime popup permission during user gesture so open_url works later
    const testPopup = window.open("about:blank", "_blank");
    if (testPopup) testPopup.close();

    if (isConnected && gemini) {
      await gemini.disconnect();
      await narration?.disconnect();
      audioManager?.stopCapture();
      ui.setConnected(false);
      isConnected = false;
      return;
    }
    await connectGemini();
  });

  // Mode selector — needed for initial state
  const modeSelect = document.getElementById("mode-select") as HTMLSelectElement;
  audioManager.setMode(modeSelect.value as any);

  // Auto-connect Gemini
  await connectGemini();

  voiceReady = true;
}

// ── Modelos (agente e voz) ───────────────────────────────────

async function setupModelSettings(): Promise<void> {
  const modelSelect = document.getElementById("model-select") as HTMLSelectElement;
  const effortSelect = document.getElementById("effort-select") as HTMLSelectElement;
  const voiceSelect = document.getElementById("voice-model-select") as HTMLSelectElement;

  const modeLabel = () =>
    modelSelect.value === "auto" ? "Automático" : (modelSelect.selectedOptions[0]?.textContent || modelSelect.value);

  try {
    const res = await fetch("/api/models");
    const data = await res.json();

    modelSelect.innerHTML = "";
    const auto = data.agent.find((m: any) => m.id === "auto");
    if (auto) modelSelect.appendChild(new Option(auto.label, auto.id));
    for (const tier of ["rapido", "padrao", "forte"]) {
      const models = data.agent.filter((m: any) => m.tier === tier);
      if (!models.length) continue;
      const group = document.createElement("optgroup");
      group.label = `Fixar — ${data.tiers[tier]}`;
      for (const m of models) group.appendChild(new Option(`${m.label} (${m.provider})`, m.id));
      modelSelect.appendChild(group);
    }
    voiceSelect.innerHTML = "";
    for (const v of data.voice) voiceSelect.appendChild(new Option(v.label, v.id));

    modelSelect.value = data.current.agent_model || "auto";
    effortSelect.value = data.current.agent_effort || "high";
    if (data.current.voice_model) voiceSelect.value = data.current.voice_model;
    ui.setRouteMode(modeLabel());
  } catch (err) {
    log("UI", `Failed to load models: ${err}`);
  }

  const saveConfig = async (body: Record<string, string>) => {
    const res = await fetch("/api/agent-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.error) ui.addStatus(`Ajuste recusado: ${data.error}`);
    return data;
  };

  modelSelect.addEventListener("change", async () => {
    await saveConfig({ model: modelSelect.value });
    ui.setRouteMode(modeLabel());
    ui.addStatus(`Modelo do agente: ${modeLabel()}`);
  });
  effortSelect.addEventListener("change", async () => {
    await saveConfig({ effort: effortSelect.value });
    ui.addStatus(`Esforço do agente: ${effortSelect.selectedOptions[0]?.textContent}`);
  });
  voiceSelect.addEventListener("change", async () => {
    await saveConfig({ voice_model: voiceSelect.value });
    ui.addStatus(`Modelo de voz: ${voiceSelect.selectedOptions[0]?.textContent} — reconectando…`);
    if (voiceReady) await connectGemini();
  });
}

async function connectGemini(): Promise<void> {
  if (!audioManager) return;
  const langSelect = document.getElementById("language-select") as HTMLSelectElement;

  // Close existing session if any
  if (gemini) {
    await gemini.disconnect();
  }

  gemini = new GeminiConnection(audioManager, {
    onTranscript: (role, text) => {
      ui.addTranscript(role, text);
      
      // Protocolo Vingador Detection
      if (role === "user") {
        const lower = text.toLowerCase();
        if (lower.includes("protocolo vingador")) {
          document.body.classList.add("vingador");
          log("PROTOCOL", "AVENGER PROTOCOL ACTIVATED");
          ui.showProtocolActivation("vingador");
          playProtocolMusic("/audio/back_in_black.mp3");
        } else if (lower.includes("descansar") || lower.includes("protocolo padrão") || lower.includes("protocolo jarvis")) {
          document.body.classList.remove("vingador");
          log("PROTOCOL", "STAND DOWN - DEFAULT PROTOCOLS RESTORED");
          stopProtocolMusic();
        }
      }
    },
    onTurnComplete: () => {
      ui.endTranscript();
    },
    onWakeWordDetected: () => {
      ui.showWakeActive();
    },
    onStandbyMode: () => {
      ui.showStandby();
    },
    onInterrupted: () => {
      ui.endTranscript();
      ui.addStatus("Você interrompeu a fala");
    },
    onThinking: (text) => {
      ui.addGeminiThinking(text);
    },
    onFunctionCall: (id, name, args) => {
      log("GEMINI", `function_call name=${name} id=${id} | ${JSON.stringify(args).slice(0, 150)}`);

      // Log to Gemini tab
      ui.addGeminiToolCall(name, args);

      // End current transcript so Gemini's post-tool response starts a new turn
      ui.endTranscript();

      // Client-side tools — handled in browser, not sent to Agent
      if (name === "open_url") {
        const url = (args.url as string) || "";
        log("BROWSER", `open_url called with: ${url}`);
        
        let result = "";
        let isError = false;
        
        if (!url) {
          result = "Error: No URL provided";
          isError = true;
        } else {
          try {
            // Method 1: window.open
            const newWindow = window.open(url, "_blank");
            if (newWindow) {
              result = `Successfully opened ${url} in a new browser tab.`;
              log("BROWSER", "window.open succeeded");
            } else {
              throw new Error("window.open returned null");
            }
          } catch (e) {
            log("BROWSER", `window.open failed: ${e}, trying fallback...`);
            
            // Method 2: Anchor element click
            try {
              const a = document.createElement("a");
              a.href = url;
              a.target = "_blank";
              a.rel = "noopener noreferrer";
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              result = `Successfully opened ${url} in a new browser tab.`;
              log("BROWSER", "anchor click succeeded");
            } catch (e2) {
              result = `Failed to open ${url}. This may be due to popup blocker. Please allow popups for this site.`;
              isError = true;
              log("BROWSER", `anchor click also failed: ${e2}`);
            }
          }
        }
        
        log("BROWSER", `Final result: ${result}`);
        
        if (gemini) {
          gemini.sendFunctionResponse(id, name, result);
        }
        ui.addGeminiToolResult(name, result, isError);
        return;
      }

      if (name === "generate_image") {
        if (!nvidiaApi) {
          const err = "NVIDIA API not configured (missing key)";
          gemini!.sendFunctionResponse(id, name, err);
          ui.addGeminiToolResult(name, err, true);
          return;
        }

        const prompt = (args.prompt as string) || "";
        log("NVIDIA", `Generating image: ${prompt}`);
        ui.addStatus("Generating image with NVIDIA Picasso...");

        nvidiaApi.generateImage({
          prompt,
          negativePrompt: (args.negativePrompt as string),
          aspectRatio: (args.aspectRatio as any)
        })
          .then((res) => {
            if (res.images && res.images.length > 0) {
              const base64 = res.images[0];
              ui.addGeminiImage(prompt, base64);
              gemini!.sendFunctionResponse(id, name, `Image generated successfully for prompt: ${prompt}`);
              ui.addStatus("Image generated successfully");
            } else {
              const err = "NVIDIA API returned no images";
              gemini!.sendFunctionResponse(id, name, err);
              ui.addGeminiToolResult(name, err, true);
            }
          })
          .catch((err) => {
            log("NVIDIA", `Generation failed: ${err}`);
            gemini!.sendFunctionResponse(id, name, `Failed to generate image: ${err.message || err}`);
            ui.addGeminiToolResult(name, `Failed: ${err.message || err}`, true);
          });
        return;
      }

      if (name === "rewind") {
        const hash = (args.hash as string) || "";

        if (!hash) {
          // List checkpoints
          fetch("/api/checkpoints")
            .then((r) => r.json())
            .then((data) => {
              if (!data.checkpoints || data.checkpoints.length === 0) {
                gemini!.sendFunctionResponse(id, name, "No checkpoints available. No code changes have been made yet.");
              } else {
                const list = data.checkpoints
                  .map((c: any) => `${c.hash}: ${c.label} (${c.when})`)
                  .join("\n");
                gemini!.sendFunctionResponse(id, name, `Available checkpoints (most recent first):\n${list}\n\nTo restore, call rewind with the hash of the checkpoint you want to go back to.`);
              }
              // Show checkpoints in timeline
              if (data.checkpoints?.length > 0) {
                const display = data.checkpoints.map((c: any) => `${c.hash} — ${c.label} (${c.when})`).join("\n");
                ui.addStatus(`Checkpoints:\n${display}`);
              }
              ui.addGeminiToolResult(name, `Listed ${data.checkpoints?.length || 0} checkpoints`, false);
            })
            .catch((err) => {
              gemini!.sendFunctionResponse(id, name, `Failed to list checkpoints: ${err}`);
              ui.addGeminiToolResult(name, `Failed: ${err}`, true);
            });
        } else {
          // Restore to checkpoint
          log("REWIND", `Restoring to checkpoint ${hash}`);
          fetch("/api/checkpoints/restore", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hash }),
          })
            .then((r) => r.json())
            .then((data) => {
              if (data.ok) {
                const msg = `Code rewound to checkpoint ${hash}. A safety checkpoint was created before the rewind in case you want to undo the undo.`;
                gemini!.sendFunctionResponse(id, name, msg);
                ui.addGeminiToolResult(name, msg, false);
              } else {
                gemini!.sendFunctionResponse(id, name, `Rewind failed: ${data.error}`);
                ui.addGeminiToolResult(name, `Failed: ${data.error}`, true);
              }
            })
            .catch((err) => {
              gemini!.sendFunctionResponse(id, name, `Rewind failed: ${err}`);
              ui.addGeminiToolResult(name, `Failed: ${err}`, true);
            });
        }
        return;
      }

      if (name === "set_agent_model") {
        const model = (args.model as string) || "";
        const effort = (args.effort as string) || "";

        if (!model && !effort) {
          // No params — return current config and available options
          fetch("/api/agent-config")
            .then((r) => r.json())
            .then((data) => {
              const msg = `Current config: model=${data.model}, effort=${data.effort}. Use model 'auto' for per-task routing, or pin one of: google/gemini-flash-lite-latest, google/gemini-flash-latest, google/gemini-pro-latest, nvidia/z-ai/glm-5.3, nvidia/nvidia/nemotron-3-super-120b-a12b, nvidia/moonshotai/kimi-k3. Efforts: low, medium, high, max.`;
              gemini!.sendFunctionResponse(id, name, msg);
              ui.addGeminiToolResult(name, msg, false);
            })
            .catch((err) => {
              gemini!.sendFunctionResponse(id, name, `Failed to get config: ${err}`);
              ui.addGeminiToolResult(name, `Failed: ${err}`, true);
            });
        } else {
          log("CONFIG", `Setting Agent model=${model} effort=${effort}`);
          fetch("/api/agent-config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model, effort }),
          })
            .then((r) => r.json())
            .then((data) => {
              const msg = data.error ? `Failed: ${data.error}` : `Agent config updated: model=${data.model}, effort=${data.effort}`;
              const sel = document.getElementById("model-select") as HTMLSelectElement | null;
              if (sel && data.model) { sel.value = data.model; ui.setRouteMode(data.model === "auto" ? "Automático" : (sel.selectedOptions[0]?.textContent || data.model)); }
              gemini!.sendFunctionResponse(id, name, msg);
              ui.addGeminiToolResult(name, msg, false);
            })
            .catch((err) => {
              gemini!.sendFunctionResponse(id, name, `Failed to update config: ${err}`);
              ui.addGeminiToolResult(name, `Failed: ${err}`, true);
            });
        }
        return;
      }

      if (name === "cancel_task") {
        fetch("/api/cancel", { method: "POST" })
          .then((r) => r.json())
          .then((data) => {
            const msg = data.message || "Operation cancelled";
            gemini!.sendFunctionResponse(id, name, msg);
            ui.addGeminiToolResult(name, msg, false);
            ui.setAgentWorking(false);
            narration?.silence();
            ui.addStatus("Agent operation cancelled");
          })
          .catch((err) => {
            gemini!.sendFunctionResponse(id, name, `Cancel failed: ${err}`);
            ui.addGeminiToolResult(name, `Failed: ${err}`, true);
          });
        return;
      }

      ui.setAgentWorking(true);
      ui.addStatus(`Agent working on ${name}...`);
      // Unmute narration — main Gemini is now waiting for function response
      narration?.unmute();
      narration?.sendImmediate(`Agent is starting to work on: ${name}. Instruction: ${JSON.stringify(args).slice(0, 200)}`);
      backend!.sendFunctionCall(id, name, args);
    },
    onConnected: () => {
      ui.setConnected(true);
      isConnected = true;
      ui.addStatus("Jarvis conectado");
    },
    onDisconnected: () => {
      ui.setConnected(false);
      isConnected = false;
      ui.addStatus("Voz desconectada");
    },
    onStateChange: (state) => {
      ui.setGeminiState(state);
    },
  }, langSelect?.value || "en-US");

  await gemini.connect();

  // DISABLED: NarrationConnection creates its own internal AudioContext via the
  // Gemini SDK. On Windows, having 3+ AudioContexts (ours + Gemini main + Narration)
  // causes "The AudioContext encountered an error from the audio device" crash.
  // Pattern inspired by jarvis-tutorial: single audio stream, no competing contexts.
  log("NARRATION", "Narration disabled for audio stability (single AudioContext pattern)");
  narration = null;
}


function addImageAttachment(file: File): void {
  const previewArea = document.getElementById("attachment-preview")!;
  const reader = new FileReader();
  reader.onload = () => {
    const dataUrl = reader.result as string;
    const base64 = dataUrl.split(",")[1];
    const mimeType = file.type || "image/png";
    pendingImages.push({ mimeType, data: base64 });

    const thumb = document.createElement("div");
    thumb.className = "attachment-thumb";
    const idx = pendingImages.length - 1;
    thumb.innerHTML = `<img src=\"${dataUrl}\" /><button class=\"attachment-remove\" data-idx=\"${idx}\">\u00D7</button>`;
    previewArea.appendChild(thumb);

    thumb.querySelector(".attachment-remove")!.addEventListener("click", () => {
      pendingImages.splice(idx, 1);
      thumb.remove();
    });
  };
  reader.readAsDataURL(file);
}

// ── Static UI Listeners (Setup Once) ─────────────────────────

function setupStaticUI(): void {
  const modeSelect = document.getElementById("mode-select") as HTMLSelectElement;
  const textInput = document.getElementById("text-input") as HTMLInputElement;
  const attachBtn = document.getElementById("attach-btn")!;
  const fileInput = document.getElementById("file-input") as HTMLInputElement;
  const previewArea = document.getElementById("attachment-preview")!;
  const micBtn = document.getElementById("mic-btn")!;
  const newChatBtn = document.getElementById("new-chat-btn")!;

  modeSelect.addEventListener("change", () => {
    const mode = modeSelect.value as "push-to-talk" | "toggle" | "always-on";
    audioManager?.setMode(mode);
    const hints: Record<string, string> = {
      "push-to-talk": "Segure Espaço para falar",
      "toggle": "Toque em Espaço para falar",
      "always-on": "Ouvindo…",
    };
    const hintEl = document.getElementById("mic-hint");
    if (hintEl) hintEl.textContent = hints[mode];
  });

  attachBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", () => {
    if (fileInput.files) {
      for (const file of Array.from(fileInput.files)) {
        addImageAttachment(file);
      }
      fileInput.value = "";
    }
  });

  textInput.addEventListener("paste", (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) addImageAttachment(file);
      }
    }
  });

  textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && gemini) {
      const text = textInput.value.trim();
      if (!text && pendingImages.length === 0) return;

      const label = text || `[${pendingImages.length} screenshot(s)]`;
      ui.addTranscript("user", label);
      gemini.sendText(text, pendingImages.length > 0 ? pendingImages : undefined);
      textInput.value = "";
      pendingImages = [];
      previewArea.innerHTML = "";
    }
  });

  micBtn.addEventListener("click", async () => {
    if (!audioManager) {
      log("UI", "Audio manager not ready, initializing...");
      audioManager = new AudioManager();
      await audioManager.init();
    }
    try {
      await audioManager.toggleCapture();
    } catch (err) {
      log("UI", "Error toggling capture: " + err);
    }
  });

  newChatBtn.addEventListener("click", async () => {
    if (gemini) {
      gemini.clearSessionHandle();
      await gemini.disconnect();
    }
    if (narration) {
      await narration.disconnect();
    }
    audioManager?.stopCapture();
    ui.setConnected(false);
    isConnected = false;
    // Clear stored session handle on backend
    fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gemini_handle: null }),
    }).catch(() => {});
    ui.clearAll();
    ui.addStatus("Contexto limpo — nova sessão");
    await connectGemini();
  });
}

// ── Teardown ─────────────────────────────────────────────────

function teardownVoiceUI(): void {
  gemini?.disconnect();
  narration?.disconnect();
  backend?.disconnect();
  audioManager?.destroy();
  gemini = null;
  narration = null;
  backend = null;
  audioManager = null;
  isConnected = false;
  voiceReady = false;
}

// ── Main Init ────────────────────────────────────────────────

async function init() {
  // AudioManager is NOT created here — it's lazy-initialized in initVoiceUI()
  // to avoid competing for hardware resources before the user interacts.

  setupStaticUI();

  // Janela de projeto (aberta pelo nome do projeto no cabeçalho)
  ui.onOpenProject((path) => openProject(path));
  ui.onBrowseNative(async () => {
    try {
      const res = await fetch("/api/projects/pick");
      const data = await res.json();
      if (data.path) {
        openProject(data.path);
      }
    } catch {
      // dialog cancelled or failed
    }
  });
  ui.onChangeProject(() => openProjectPicker());
  ui.onBrowseDir((path) => browseDir(path));
  ui.onSelectDir((path) => openProject(path));
  ui.onRecentClick((path) => openProject(path));

  await setupModelSettings();

  // O servidor sempre abre um projeto ao iniciar; a janela só aparece se algo falhar
  try {
    const res = await fetch("/api/project");
    const data = await res.json();

    if (data.active && data.path) {
      currentProject = data.path;
      ui.showVoiceScreen(data.path);
      await initVoiceUI();
    } else {
      await openProjectPicker();
    }
  } catch {
    await openProjectPicker();
  }

  console.log("APP", "VoiceClaw v2.3 — StableTurn (VAD manual fix)");
}

init().catch(console.error);
