/**
 * UI — DOM manipulation for transcript, unified timeline, and filters.
 */

import { marked } from "marked";
import type { AgentToolUseEvent, AgentTextEvent } from "./types";

// Configure marked for inline rendering
marked.setOptions({ breaks: true });

// Event categories — used for filtering and styling
type EventCategory =
  | "gemini-thinking"
  | "gemini-tool-call"
  | "gemini-tool-result"
  | "gemini-tool-error"
  | "gemini-summarize"
  | "agent-tool"
  | "agent-done"
  | "agent-error"
  | "agent-thinking"
  | "agent-text"
  | "file-change"
  | "status";

// Map visual categories to their filter group
const FILTER_MAP: Record<EventCategory, string> = {
  "gemini-thinking": "gemini-thinking",
  "gemini-tool-call": "gemini-tool-call",
  "gemini-tool-result": "gemini-tool-result",
  "gemini-tool-error": "gemini-tool-result",
  "gemini-summarize": "gemini-tool-result",
  "agent-tool": "agent-tool",
  "agent-done": "agent-tool",
  "agent-error": "agent-tool",
  "agent-thinking": "agent-thinking",
  "agent-text": "agent-tool",
  "file-change": "file-change",
  "status": "status",
};

export class UI {
  private transcriptEl: HTMLElement;
  private timeline: HTMLElement;
  private statusDot: HTMLElement;
  private statusText: HTMLElement;
  private micBtn: HTMLElement;
  private micHint: HTMLElement;
  private connectBtn: HTMLElement;

  // Screens
  private pickerScreen: HTMLElement;
  private voiceScreen: HTMLElement;

  // Picker elements
  private projectPathInput: HTMLInputElement;
  private browserList: HTMLElement;
  private browserHeader: HTMLElement;
  private recentProjectsEl: HTMLElement;
  private projectNameEl: HTMLElement;

  // Skills Modal
  private skillsBtn: HTMLElement;
  private skillsModal: HTMLElement;
  private closeSkillsBtn: HTMLElement;

  // Dashboard
  private dashboardOverlay: HTMLElement;
  private dashboardBtn: HTMLElement;
  private closeDashboardBtn: HTMLElement;
  private dashboardRefreshInterval: number | null = null;

  // Protocol Overlay
  private protocolOverlay: HTMLElement;

  // Task/Search counters
  private _tasksCount = 0;
  private _searchesCount = 0;

  // Filter state
  private filters: Record<string, boolean> = {};

  // Voice Block tracking
  private currentVoiceBlock: HTMLElement | null = null;

  constructor() {
    this.transcriptEl = document.getElementById("transcript")!;
    this.timeline = document.getElementById("timeline")!;
    this.statusDot = document.getElementById("connection-status")!;
    this.statusText = document.getElementById("status-text")!;
    this.micBtn = document.getElementById("mic-btn")!;
    this.micHint = document.getElementById("mic-hint")!;
    this.connectBtn = document.getElementById("connect-btn")!;

    this.pickerScreen = document.getElementById("project-picker")!;
    this.voiceScreen = document.getElementById("voice-screen")!;
    this.projectPathInput = document.getElementById("project-path") as HTMLInputElement;
    this.browserList = document.getElementById("browser-list")!;
    this.browserHeader = document.getElementById("browser-header")!;
    this.recentProjectsEl = document.getElementById("recent-projects")!;
    this.projectNameEl = document.getElementById("project-name")!;
    
    // Canvas elements
    this.canvasContent = document.getElementById("canvas-content")!;
    
    // Skills elements
    this.skillsBtn = document.getElementById("skills-btn")!;
    this.skillsModal = document.getElementById("skills-modal")!;
    this.closeSkillsBtn = document.getElementById("close-skills-btn")!;

    // Dashboard elements
    this.dashboardOverlay = document.getElementById("dashboard-overlay")!;
    this.dashboardBtn = document.getElementById("dashboard-btn")!;
    this.closeDashboardBtn = document.getElementById("close-dashboard-btn")!;

    // Protocol overlay
    this.protocolOverlay = document.getElementById("protocol-overlay")!;

    this.initSkillsModal();
    this.initDashboard();
    this.initFilters();

    // Iniciar loop periódico leve em background para sincronizar subagentes e status na tela principal
    window.setInterval(() => {
      if (this.voiceScreen.style.display !== "none") {
        this.updateDashboard();
      }
    }, 3000);
  }

  private initSkillsModal(): void {
    if (this.skillsBtn && this.skillsModal && this.closeSkillsBtn) {
      this.skillsBtn.addEventListener("click", () => {
        this.skillsModal.style.display = "flex";
      });
      
      this.closeSkillsBtn.addEventListener("click", () => {
        this.skillsModal.style.display = "none";
      });
      
      this.skillsModal.addEventListener("click", (e) => {
        if (e.target === this.skillsModal) {
          this.skillsModal.style.display = "none";
        }
      });
    }
  }

  private canvasContent: HTMLElement;

  private initFilters(): void {
    const chips = document.querySelectorAll(".filter-chip");
    chips.forEach((chip) => {
      const filterName = (chip as HTMLElement).dataset.filter!;
      const checkbox = chip.querySelector("input") as HTMLInputElement;
      this.filters[filterName] = checkbox.checked;

      chip.addEventListener("click", (e) => {
        e.preventDefault();
        checkbox.checked = !checkbox.checked;
        this.filters[filterName] = checkbox.checked;
        chip.classList.toggle("unchecked", !checkbox.checked);
        this.applyFilters();
      });
    });
  }

  private applyFilters(): void {
    const entries = this.timeline.querySelectorAll(".tl-entry");
    entries.forEach((entry) => {
      const cat = (entry as HTMLElement).dataset.category as EventCategory;
      const filterGroup = FILTER_MAP[cat] || cat;
      const visible = this.filters[filterGroup] !== false;
      (entry as HTMLElement).style.display = visible ? "" : "none";
    });
  }

  onConnectClick(handler: () => void): void {
    this.connectBtn.addEventListener("click", handler);
  }

  // ── Project Picker ─────────────────────────────────────────

  showProjectPicker(): void {
    this.pickerScreen.style.display = "flex";
    this.voiceScreen.style.display = "none";
    this.renderRecentProjects();
    this.projectPathInput.focus();
  }

  showVoiceScreen(projectPath: string): void {
    this.pickerScreen.style.display = "none";
    this.voiceScreen.style.display = "flex";

    const name = projectPath.split(/[/\\]/).pop() || projectPath;
    this.projectNameEl.textContent = name;
    this.projectNameEl.title = projectPath;

    this.addRecentProject(projectPath);
  }

  onOpenProject(handler: (path: string) => void): void {
    const openBtn = document.getElementById("open-btn")!;
    const input = this.projectPathInput;

    const submit = () => {
      const path = input.value.trim();
      if (path) handler(path);
    };

    openBtn.addEventListener("click", submit);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") submit();
    });
  }

  onBrowseNative(handler: () => void): void {
    document.getElementById("browse-btn")!.addEventListener("click", handler);
  }

  onChangeProject(handler: () => void): void {
    document.getElementById("change-project-btn")!.addEventListener("click", handler);
  }

  onBrowseDir(handler: (path: string) => void): void {
    this.browserList.addEventListener("click", (e) => {
      const target = (e.target as HTMLElement).closest("[data-path]") as HTMLElement | null;
      if (target?.dataset.path) handler(target.dataset.path);
    });
    this.browserHeader.addEventListener("click", (e) => {
      const target = (e.target as HTMLElement).closest("[data-path]") as HTMLElement | null;
      if (target?.dataset.path) handler(target.dataset.path);
    });
  }

  onSelectDir(handler: (path: string) => void): void {
    this.browserList.addEventListener("dblclick", (e) => {
      const target = (e.target as HTMLElement).closest("[data-path]") as HTMLElement | null;
      if (target?.dataset.path) handler(target.dataset.path);
    });
  }

  onRecentClick(handler: (path: string) => void): void {
    this.recentProjectsEl.addEventListener("click", (e) => {
      const target = (e.target as HTMLElement).closest("[data-path]") as HTMLElement | null;
      if (target?.dataset.path) handler(target.dataset.path);
    });
  }

  renderFolderBrowser(current: string, parent: string, dirs: { name: string; path: string }[]): void {
    this.projectPathInput.value = current;

    this.browserHeader.innerHTML = `<button class="browser-up" data-path="${escapeAttr(parent)}">&#8593; Up</button>
      <span class="browser-current">${escapeHtml(current)}</span>`;

    this.browserList.innerHTML = dirs
      .map(
        (d) =>
          `<div class="browser-dir" data-path="${escapeAttr(d.path)}">&#128193; ${escapeHtml(d.name)}</div>`
      )
      .join("");
  }

  setPickerError(msg: string): void {
    this.projectPathInput.classList.add("input-error");
    this.projectPathInput.placeholder = msg;
    setTimeout(() => {
      this.projectPathInput.classList.remove("input-error");
      this.projectPathInput.placeholder = "/path/to/your/project";
    }, 2000);
  }

  private renderRecentProjects(): void {
    const recent = this.getRecentProjects();
    if (recent.length === 0) {
      this.recentProjectsEl.innerHTML = "";
      return;
    }
    this.recentProjectsEl.innerHTML =
      `<h3>Recent Projects</h3>` +
      recent
        .map((p) => {
          const name = p.split(/[/\\]/).pop() || p;
          return `<div class="recent-entry" data-path="${escapeAttr(p)}">
            <span class="recent-name">${escapeHtml(name)}</span>
            <span class="recent-path">${escapeHtml(p)}</span>
          </div>`;
        })
        .join("");
  }

  private addRecentProject(path: string): void {
    const recent = this.getRecentProjects().filter((p) => p !== path);
    recent.unshift(path);
    localStorage.setItem("voicecode_recent", JSON.stringify(recent.slice(0, 10)));
  }

  private getRecentProjects(): string[] {
    try {
      return JSON.parse(localStorage.getItem("voicecode_recent") || "[]");
    } catch {
      return [];
    }
  }

  // ── Status ──────────────────────────────────────────────────

  setConnected(connected: boolean): void {
    this.statusDot.className = `status-dot ${connected ? "connected" : "disconnected"}`;
    this.statusText.textContent = connected ? "Connected" : "Disconnected";
    this.connectBtn.textContent = connected ? "Disconnect" : "Connect";
  }

  setAgentWorking(working: boolean): void {
    if (working) {
      this.statusText.textContent = "Agent working...";
      this.statusDot.className = "status-dot recording";
    } else {
      this.statusText.textContent = "Connected";
      this.statusDot.className = "status-dot connected";
    }
  }

  setGeminiState(state: "idle" | "thinking" | "speaking" | "listening"): void {
    const labels: Record<string, string> = {
      idle: "Ready",
      thinking: "Thinking...",
      speaking: "Speaking...",
      listening: "Listening...",
    };
    const dotClass: Record<string, string> = {
      idle: "connected",
      thinking: "thinking",
      speaking: "speaking",
      listening: "recording",
    };
    this.statusText.textContent = labels[state];
    this.statusDot.className = `status-dot ${dotClass[state]}`;
  }

  // ── Transcript ──────────────────────────────────────────────

  private lastTranscriptRole: "user" | "gemini" | "narrator" | null = null;
  private lastTranscriptEl: HTMLElement | null = null;
  private lastTranscriptText = "";

  addTranscript(role: "user" | "gemini" | "narrator", text: string): void {
    if (role === this.lastTranscriptRole && this.lastTranscriptEl) {
      this.lastTranscriptText += text;
    } else {
      const entry = document.createElement("div");
      entry.className = `transcript-entry transcript-${role}`;
      const roleLabels: Record<string, string> = { user: "You", gemini: "Jarvis", narrator: "Jarvis (Thinking)" };
      const roleLabel = roleLabels[role] || role;
      entry.innerHTML = `<span class="role">${roleLabel}:</span> <span class="transcript-text"></span>`;

      this.transcriptEl.appendChild(entry);
      this.lastTranscriptRole = role;
      this.lastTranscriptEl = entry;
      this.lastTranscriptText = text;
    }

    const textSpan = this.lastTranscriptEl!.querySelector(".transcript-text") as HTMLElement;
    if (textSpan) {
      if (role === "gemini" || role === "narrator") {
        const result = this.extractCodeAndClean(this.lastTranscriptText);
        textSpan.innerHTML = result.cleanHtml; // Use innerHTML for ref tags
        if (result.hasCode) {
          // If we don't have a block for this speech yet, create it
          if (!this.currentVoiceBlock) {
            this.currentVoiceBlock = document.createElement("div");
            this.currentVoiceBlock.className = "canvas-voice-block";
            this.canvasContent.innerHTML += `<div class="canvas-block-sep"></div>`;
            this.canvasContent.appendChild(this.currentVoiceBlock);
          }
          
          // Update the content of the current block
          this.currentVoiceBlock.innerHTML = result.canvasHtml;
          this.attachSaveButtonListeners();
          this.canvasContent.scrollTop = this.canvasContent.scrollHeight;
        }

      } else {
        textSpan.textContent = this.lastTranscriptText;
      }
    }

    this.transcriptEl.scrollTop = this.transcriptEl.scrollHeight;
  }

  endTranscript(): void {
    // If it was the agent, we might want to keep the canvas state
    this.lastTranscriptRole = null;
    this.lastTranscriptEl = null;
    this.lastTranscriptText = "";
    this.currentVoiceBlock = null; // Reset voice block for next speech
  }

  replaceLastUserTranscript(text: string): void {
    const entries = this.transcriptEl.querySelectorAll(".transcript-user");
    const last = entries[entries.length - 1];
    if (last) {
      const textSpan = last.querySelector(".transcript-text");
      if (textSpan) {
        textSpan.textContent = text;
        last.classList.remove("transcript-draft");
      }
    }
  }

  markLastAsDraft(): void {
    if (this.lastTranscriptEl && this.lastTranscriptRole === "user") {
      this.lastTranscriptEl.classList.add("transcript-draft");
    }
  }

  // ── Unified Timeline ──────────────────────────────────────

  private appendTimeline(category: EventCategory, tag: string, detail: string, renderMarkdown = false): void {
    const entry = document.createElement("div");
    entry.className = `tl-entry cat-${category}`;
    entry.dataset.category = category;

    const time = this.timeStamp();
    const filterGroup = FILTER_MAP[category] || category;
    const visible = this.filters[filterGroup] !== false;
    if (!visible) entry.style.display = "none";

    if (renderMarkdown && looksLikeMarkdown(detail)) {
      const rendered = marked.parse(detail) as string;
      entry.innerHTML = `<span class="tl-time">${time}</span> <span class="tl-tag">${escapeHtml(tag)}</span> <span class="tl-detail md-content">${rendered}</span>`;
    } else {
      entry.innerHTML = `<span class="tl-time">${time}</span> <span class="tl-tag">${escapeHtml(tag)}</span> <span class="tl-detail">${escapeHtml(detail)}</span>`;
    }

    this.timeline.appendChild(entry);
    this.timeline.scrollTop = this.timeline.scrollHeight;
  }

  private timeStamp(): string {
    return new Date().toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  // Gemini events
  addGeminiThinking(text: string): void {
    this.appendTimeline("gemini-thinking", "Thinking", text);
  }

  addGeminiToolCall(name: string, args: Record<string, unknown>): void {
    const argsPreview = JSON.stringify(args).slice(0, 120);
    this.appendTimeline("gemini-tool-call", "Tool Call", `${name}(${argsPreview})`);
  }

  addGeminiToolResult(name: string, result: string, isError: boolean): void {
    const cat: EventCategory = isError ? "gemini-tool-error" : "gemini-tool-result";
    const tag = isError ? "Error" : "Result";
    this.appendTimeline(cat, tag, result, true);
  }

  addGeminiImage(prompt: string, base64Data: string): void {
    const entry = document.createElement("div");
    entry.className = `tl-entry cat-gemini-tool-result`;
    entry.dataset.category = "gemini-tool-result";

    const time = this.timeStamp();
    entry.innerHTML = `
      <span class="tl-time">${time}</span> 
      <span class="tl-tag">Image</span> 
      <div class="tl-detail">
        <p><em>${escapeHtml(prompt)}</em></p>
        <img src="data:image/png;base64,${base64Data}" class="generated-image" style="max-width: 100%; border-radius: 8px; margin-top: 8px; cursor: pointer;" />
      </div>`;
    
    // Click to open full size
    entry.querySelector("img")?.addEventListener("click", () => {
      const win = window.open();
      win?.document.write(`<img src="data:image/png;base64,${base64Data}" style="max-width: 100vw;" />`);
    });

    this.timeline.appendChild(entry);
    this.timeline.scrollTop = this.timeline.scrollHeight;
    
    // Also update canvas
    this.updateLiveCanvas(`
      <div class="canvas-image">
        <h4>Generated Image</h4>
        <p><em>${escapeHtml(prompt)}</em></p>
        <img src="data:image/png;base64,${base64Data}" style="max-width: 100%; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);" />
      </div>
    `);
  }

  addGeminiSummarize(functionName: string): void {
    this.appendTimeline("gemini-summarize", "Summarizing", `Relaying Agent's ${functionName} response`);
  }

  // Agent events
  addActivityEvent(event: AgentToolUseEvent): void {
    const icon = toolIcon(event.tool);
    let detail = "";

    if (event.tool === "Read" || event.tool === "Edit" || event.tool === "Write") {
      detail = (event.input.file_path as string) || event.tool;
    } else if (event.tool === "Bash") {
      detail = ((event.input.command as string) || "").slice(0, 80);
    } else if (event.tool === "Glob" || event.tool === "Grep") {
      detail = (event.input.pattern as string) || "search";
    } else {
      detail = event.tool;
    }

    this.appendTimeline("agent-tool", `${icon} ${event.tool}`, detail);

    // Also add inline diffs for Edit/Write
    if (event.tool === "Edit") {
      this.addDiff(
        (event.input.file_path as string) || "unknown",
        (event.input.old_string as string) || "",
        (event.input.new_string as string) || ""
      );
    } else if (event.tool === "Write") {
      this.addDiff(
        (event.input.file_path as string) || "unknown",
        "",
        (event.input.content as string) || ""
      );
    }
  }

  addActivityDone(isError: boolean): void {
    const cat: EventCategory = isError ? "agent-error" : "agent-done";
    const tag = isError ? "Error" : "Done";
    this.appendTimeline(cat, tag, isError ? "Task failed" : "Task completed");
  }

  addAgentThinking(text: string): void {
    this.appendTimeline("agent-thinking", "Agent Thinking", text, true);
  }

  addAgentText(text: string): void {
    const result = this.extractCodeAndClean(text);
    this.appendTimeline("agent-text", "Agent", result.cleanHtml, true);
    
    if (result.hasCode || result.isAnalysis) {
      this.updateLiveCanvas(result.canvasHtml, true); // Append content
    }
  }

  /**
   * Core logic to separate UI text from Canvas content
   */
  private extractCodeAndClean(text: string): { cleanHtml: string, canvasHtml: string, hasCode: boolean, isAnalysis: boolean } {
    const codeBlockRegex = /```(\w*)[\s\n]*([\s\S]*?)```/g;
    let match;
    let hasCode = false;
    let canvasHtml = "";
    let cleanText = text;

    while ((match = codeBlockRegex.exec(text)) !== null) {
      hasCode = true;
      const language = match[1] || "code";
      const code = match[2];
      
      canvasHtml += `<div class="canvas-header-lang">${language.toUpperCase()}</div>`;
      
      // If it's HTML, wrap it in an iframe for isolation
      if (language.toLowerCase() === 'html') {
          canvasHtml += `
            <div class="canvas-render-box">
              <iframe sandbox="allow-scripts allow-modals" srcdoc="${escapeAttr(code)}" style="width:100%; height:400px; border:none; background:white; border-radius:4px;"></iframe>
            </div>`;
      } else if (language.toLowerCase() === 'svg') {
          const isSvg = language.toLowerCase() === 'svg';
          const displayCode = isSvg && !code.trim().startsWith('<svg') 
            ? `<svg viewBox="0 0 100 100" style="width:100%; height:auto;">${code}</svg>` 
            : code;
          canvasHtml += `<div class="canvas-render-box">${displayCode}</div>`;
      }

      canvasHtml += `
        <div class="canvas-code-wrapper">
          <pre><code>${escapeHtml(code)}</code></pre>
          <div class="canvas-actions">
            <button class="canvas-btn canvas-unified-save-btn" data-code="${escapeAttr(code)}" data-lang="${language}">💾 Save File</button>
          </div>
        </div>`;

      cleanText = cleanText.replace(match[0], `<span class="canvas-ref-tag">[View ${language.toUpperCase()} in Canvas]</span>`);
    }

    let isAnalysis = false;
    if (!hasCode && text.length > 40) {
      isAnalysis = true;
      const rendered = marked.parse(text) as string;
      canvasHtml = `<div class="canvas-md">${rendered}</div>`;
      if (text.length > 150) {
        cleanText = text.slice(0, 100) + "... " + `<span class="canvas-ref-tag">[Full Analysis in Canvas]</span>`;
      }
    }

    return {
      cleanHtml: hasCode || (isAnalysis && text.length > 150) ? cleanText : escapeHtml(text),
      canvasHtml,
      hasCode,
      isAnalysis
    };
  }

  // ── Canvas Management ──────────────────────────────────────

  updateLiveCanvas(html: string, append: boolean = true): void {
    if (!this.canvasContent) return;
    if (append) {
      this.canvasContent.innerHTML += `<div class="canvas-block-sep"></div>` + html;
    } else {
      this.canvasContent.innerHTML = html;
    }

    // Attach listeners to any new save buttons
    this.attachSaveButtonListeners();
    this.canvasContent.scrollTop = this.canvasContent.scrollHeight;
  }

  private attachSaveButtonListeners(): void {
    const buttons = this.canvasContent.querySelectorAll(".canvas-unified-save-btn:not([data-attached])");
    buttons.forEach((btn) => {
      btn.setAttribute("data-attached", "true");
      btn.addEventListener("click", async () => {
        const code = (btn as HTMLElement).dataset.code || "";
        const lang = (btn as HTMLElement).dataset.lang || "txt";
        
        try {
          // Use modern Browser API for native file picker
          if ('showSaveFilePicker' in window) {
            const handle = await (window as any).showSaveFilePicker({
              suggestedName: `generated_file.${lang}`,
              types: [{
                description: 'Code File',
                accept: { 'text/plain': [`.${lang}`, '.txt', '.js', '.py', '.html', '.css'] },
              }],
            });
            const writable = await handle.createWritable();
            await writable.write(code);
            await writable.close();
          } else {
            // Fallback for older browsers
            const fn = prompt("Seu navegador não suporta o seletor nativo. Digite o nome do arquivo:", `file.${lang}`);
            if (fn && (window as any).backend) {
              (window as any).backend.sendFunctionCall(
                "canvas_save_" + Date.now(),
                "save_canvas_file",
                { path: fn, content: code }
              );
            }
          }
        } catch (err: any) {
          if (err.name !== 'AbortError') {
            console.error("Erro ao salvar:", err);
            alert("Erro ao salvar arquivo.");
          }
        }
      });
    });
  }

  clearCanvas(): void {
    if (this.canvasContent) {
      this.canvasContent.innerHTML = `
        <div class="canvas-empty-state">
          <div class="canvas-empty-icon">JARVIS</div>
          <p>Workspace cleared. Ready for next task.</p>
        </div>
      `;
    }
  }

  // ── Timeline Management ─────────────────────────────────────

  // Clear all transcript and timeline content
  clearAll(): void {
    this.transcriptEl.innerHTML = "";
    this.timeline.innerHTML = "";
    this.lastTranscriptRole = null;
    this.lastTranscriptEl = null;
    this.lastTranscriptText = "";
    this.clearCanvas();
  }

  // Status events
  addStatus(message: string): void {
    this.appendTimeline("status", "Status", message);
  }

  // File changes (inline diffs)
  addDiff(filePath: string, oldStr: string, newStr: string): void {
    const entry = document.createElement("div");
    entry.className = "tl-entry cat-file-change";
    entry.dataset.category = "file-change";

    const time = this.timeStamp();
    const filterGroup = FILTER_MAP["file-change"];
    const visible = this.filters[filterGroup] !== false;
    if (!visible) entry.style.display = "none";

    const label = oldStr === "" ? "new" : "modified";

    const lineCount = (oldStr ? oldStr.split("\n").length : 0) + newStr.split("\n").length;

    let diffHtml = `<div class="tl-row"><span class="tl-time">${time}</span> <span class="tl-tag">File ${label}</span> <span class="tl-detail">${escapeHtml(filePath)}</span><button class="tl-diff-toggle">\u25B6 ${lineCount} lines</button></div>`;
    diffHtml += `<div class="tl-diff-body collapsed">`;

    if (oldStr) {
      for (const line of oldStr.split("\n")) {
        diffHtml += `<div class="diff-removed">- ${escapeHtml(line)}</div>`;
      }
    }
    for (const line of newStr.split("\n")) {
      diffHtml += `<div class="diff-added">+ ${escapeHtml(line)}</div>`;
    }
    diffHtml += `</div>`;

    entry.innerHTML = diffHtml;

    const toggle = entry.querySelector(".tl-diff-toggle")!;
    const body = entry.querySelector(".tl-diff-body")!;
    toggle.addEventListener("click", () => {
      const collapsed = body.classList.toggle("collapsed");
      toggle.textContent = collapsed ? `\u25B6 ${lineCount} lines` : `\u25BC ${lineCount} lines`;
    });

    this.timeline.appendChild(entry);
    this.timeline.scrollTop = this.timeline.scrollHeight;

    // Send the diff to Live Canvas for visual focus
    let canvasHtml = `<h4>File Modified: ${escapeHtml(filePath)}</h4>`;
    canvasHtml += `<div class="canvas-diff">`;
    if (oldStr) {
      for (const line of oldStr.split("\n")) {
        canvasHtml += `<div class="diff-removed">- ${escapeHtml(line)}</div>`;
      }
    }
    for (const line of newStr.split("\n")) {
      canvasHtml += `<div class="diff-added">+ ${escapeHtml(line)}</div>`;
    }
    canvasHtml += `</div>`;
    this.updateLiveCanvas(canvasHtml);
  }

  // ── Clear ───────────────────────────────────────────────────

  clearTimeline(): void {
    this.timeline.innerHTML = "";
  }

  // ── Dashboard ──────────────────────────────────────────────

  private initDashboard(): void {
    if (this.dashboardBtn && this.dashboardOverlay && this.closeDashboardBtn) {
      this.dashboardBtn.addEventListener("click", () => this.openDashboard());
      this.closeDashboardBtn.addEventListener("click", () => this.closeDashboard());
      this.dashboardOverlay.addEventListener("click", (e) => {
        if (e.target === this.dashboardOverlay) this.closeDashboard();
      });
    }
  }

  openDashboard(): void {
    this.dashboardOverlay.style.display = "flex";
    this.updateDashboard();
    // Auto-refresh every 5 seconds while open
    this.dashboardRefreshInterval = window.setInterval(() => this.updateDashboard(), 5000);
  }

  closeDashboard(): void {
    this.dashboardOverlay.style.display = "none";
    if (this.dashboardRefreshInterval) {
      clearInterval(this.dashboardRefreshInterval);
      this.dashboardRefreshInterval = null;
    }
  }

  async updateDashboard(): Promise<void> {
    try {
      const res = await fetch("/api/dashboard");
      const data = await res.json();

      // Obsidian panel
      const obsStatus = document.getElementById("obsidian-status");
      if (obsStatus) {
        obsStatus.textContent = data.obsidian?.connected ? "ONLINE" : "OFFLINE";
        obsStatus.className = `dash-status ${data.obsidian?.connected ? "online" : ""}`;
      }
      this.setDashValue("memory-count", data.obsidian?.memory_count ?? "—");
      this.setDashValue("sessions-count", data.obsidian?.sessions_count ?? "—");
      this.setDashValue("projects-count", data.obsidian?.projects_count ?? "—");
      this.setDashValue("decisions-count", data.obsidian?.decisions_count ?? "—");
      this.setDashValue("vault-path", data.obsidian?.vault_path ?? "Não configurado");

      // Recent memories
      const recentEl = document.getElementById("recent-memories");
      if (recentEl && data.obsidian?.recent) {
        recentEl.innerHTML = data.obsidian.recent.length > 0
          ? data.obsidian.recent.map((m: any) =>
              `<div class="dash-recent-item">📝 ${escapeHtml(m.preview || m.name)} <span style="opacity:0.4">${m.date || ""}</span></div>`
            ).join("")
          : `<div class="dash-recent-item" style="opacity:0.4">Nenhuma memória registrada</div>`;
      }

      // Agent panel
      const codeStatus = document.getElementById("code-agent-status");
      if (codeStatus) {
        codeStatus.textContent = data.agent?.model ? "ONLINE" : "STANDBY";
        codeStatus.className = `dash-status ${data.agent?.model ? "online" : ""}`;
      }
      this.setDashValue("active-model", data.agent?.model ?? "—");
      this.setDashValue("active-provider", data.agent?.provider?.toUpperCase() ?? "—");
      this.setDashValue("active-effort", data.agent?.effort?.toUpperCase() ?? "—");
      this.setDashValue("tasks-count", String(this._tasksCount));

      // Providers
      const providersList = document.getElementById("providers-list");
      if (providersList && data.providers) {
        providersList.innerHTML = Object.entries(data.providers)
          .map(([name, active]) =>
            `<span class="dash-provider-tag ${active ? "active" : "inactive"}">${name.toUpperCase()}</span>`
          ).join("");
      }

      // Search panel
      this.setDashValue("searches-count", String(this._searchesCount));
      this.setDashValue("obsidian-search-status", data.obsidian?.connected ? "Ativo" : "Inativo");

      const searchStatus = document.getElementById("search-agent-status");
      if (searchStatus) {
        searchStatus.textContent = "ONLINE";
        searchStatus.className = "dash-status online";
      }

      // Subagents Status Update
      const progStatus = document.getElementById("subagent-programmer-status");
      if (progStatus && data.subagents) {
        const progActive = data.subagents.programmer === "ACTIVE";
        progStatus.textContent = data.subagents.programmer;
        progStatus.className = `subagent-status ${progActive ? "active" : "standby"}`;
      }

      const desStatus = document.getElementById("subagent-designer-status");
      if (desStatus && data.subagents) {
        const desActive = data.subagents.designer === "ACTIVE";
        desStatus.textContent = data.subagents.designer;
        desStatus.className = `subagent-status ${desActive ? "active" : "standby"}`;
      }

      // Sincronização dos Mini-Badges da Tela Principal
      if (data.subagents) {
        const progActive = data.subagents.programmer === "ACTIVE";
        const mainProgBadge = document.getElementById("main-prog-badge");
        const mainProgDot = document.getElementById("main-prog-dot");
        if (mainProgBadge && mainProgDot) {
          mainProgBadge.classList.toggle("active", progActive);
          mainProgDot.className = `subagent-dot ${progActive ? "active" : "standby"}`;
          const label = mainProgBadge.querySelector(".subagent-label");
          if (label) {
            label.textContent = `💻 PROG: ${data.subagents.programmer}`;
          }
        }

        const desActive = data.subagents.designer === "ACTIVE";
        const mainDesBadge = document.getElementById("main-des-badge");
        const mainDesDot = document.getElementById("main-des-dot");
        if (mainDesBadge && mainDesDot) {
          mainDesBadge.classList.toggle("active", desActive);
          mainDesDot.className = `subagent-dot ${desActive ? "active" : "standby"}`;
          const label = mainDesBadge.querySelector(".subagent-label");
          if (label) {
            label.textContent = `🎨 DESIGN: ${data.subagents.designer}`;
          }
        }
      }

    } catch (err) {
      console.error("Dashboard update failed:", err);
    }
  }

  private setDashValue(id: string, value: string): void {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  incrementTasksCount(): void {
    this._tasksCount++;
    this.setDashValue("tasks-count", String(this._tasksCount));
  }

  incrementSearchesCount(): void {
    this._searchesCount++;
    this.setDashValue("searches-count", String(this._searchesCount));
  }

  // ── Protocol Activation ────────────────────────────────────

  showProtocolActivation(protocol: string): void {
    if (!this.protocolOverlay) return;

    // Set protocol-specific text
    const textEl = this.protocolOverlay.querySelector(".protocol-text");
    const subEl = this.protocolOverlay.querySelector(".protocol-subtext");
    const iconEl = this.protocolOverlay.querySelector(".protocol-icon");

    if (protocol === "vingador") {
      if (textEl) textEl.textContent = "PROTOCOLO VINGADOR";
      if (subEl) subEl.textContent = "ONLINE";
      if (iconEl) iconEl.textContent = "⚔️";
    } else {
      if (textEl) textEl.textContent = protocol.toUpperCase();
      if (subEl) subEl.textContent = "ATIVADO";
    }

    this.protocolOverlay.style.display = "flex";
    this.protocolOverlay.classList.add("active");

    // Remove after animation completes (~3.3s)
    setTimeout(() => {
      this.protocolOverlay.style.display = "none";
      this.protocolOverlay.classList.remove("active");
    }, 3300);
  }

  // ── Wake Word Visual ───────────────────────────────────────

  showStandby(): void {
    const voicePanel = document.getElementById("voice-panel");
    if (voicePanel) {
      voicePanel.classList.add("standby-mode");
      voicePanel.classList.remove("wake-active");
    }
    const hint = document.getElementById("mic-hint");
    if (hint) hint.textContent = 'Aguardando "Jarvis"...';
  }

  showWakeActive(): void {
    const voicePanel = document.getElementById("voice-panel");
    if (voicePanel) {
      voicePanel.classList.remove("standby-mode");
      voicePanel.classList.add("wake-active");
    }
    const hint = document.getElementById("mic-hint");
    if (hint) hint.textContent = "Ouvindo comando...";
  }

  clearWakeState(): void {
    const voicePanel = document.getElementById("voice-panel");
    if (voicePanel) {
      voicePanel.classList.remove("standby-mode", "wake-active");
    }
  }
}

// ── Helpers ──────────────────────────────────────────────────

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function escapeAttr(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function toolIcon(tool: string): string {
  const icons: Record<string, string> = {
    Read: "\u{1F4D6}",
    Edit: "\u270F\uFE0F",
    Write: "\u{1F4C4}",
    Bash: "\u{1F4BB}",
    Glob: "\u{1F50D}",
    Grep: "\u{1F50D}",
    LS: "\u{1F4C1}",
  };
  return icons[tool] || "\u2699\uFE0F";
}

/** Quick check if text contains markdown syntax worth rendering. */
function looksLikeMarkdown(text: string): boolean {
  return /[#*`\-\[\]|]/.test(text) && text.length > 30;
}
