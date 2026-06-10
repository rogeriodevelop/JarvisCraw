/**
 * GeminiConnection — Direct WebSocket to Gemini Live API from browser.
 *
 * Uses ephemeral token from backend. Handles audio I/O, function calls,
 * session resumption, and context window compression.
 */

import { GoogleGenAI, Modality } from "@google/genai";
import type { AudioManager } from "./audio-manager";
import { functionDeclarations } from "./types";
import type { ServerConfig, TokenResponse, SessionState } from "./types";
import { log, logGeminiMessage } from "./debug-log";

export interface GeminiCallbacks {
  onTranscript: (role: "user" | "gemini", text: string) => void;
  onTurnComplete: () => void;
  onInterrupted: () => void;
  onFunctionCall: (id: string, name: string, args: Record<string, unknown>) => void;
  onThinking: (text: string) => void;
  onConnected: () => void;
  onDisconnected: () => void;
  onStateChange: (state: "idle" | "thinking" | "speaking" | "listening") => void;
  onWakeWordDetected?: () => void;
  onStandbyMode?: () => void;
}

export class GeminiConnection {
  private session: any = null; // GenAI Live session
  private sessionHandle: string | null = null;
  private audioManager: AudioManager;
  private callbacks: GeminiCallbacks;
  private reconnecting = false;
  private intentionallyClosed = false;
  private isAlwaysOn = false;
  private awake = false;
  private wakeWordEnabled = false;
  private wakeTimeout: any = null;
  private readonly WAKE_TIMEOUT_MS = 5000; // 5 segundos de conversa fluente
  private currentState: "idle" | "thinking" | "speaking" | "listening" = "idle";

  private languageCode: string;

  constructor(audioManager: AudioManager, callbacks: GeminiCallbacks, languageCode: string = "en-US") {
    this.audioManager = audioManager;
    this.callbacks = callbacks;
    this.languageCode = languageCode;
  }

  async connect(): Promise<void> {
    this.intentionallyClosed = false;
    this.reconnecting = false;
    this.cancelWakeTimeout();

    try {
      // Fetch ephemeral token and config from backend
      const [tokenRes, configRes, sessionRes] = await Promise.all([
        fetch("/api/token").then((r) => r.json()) as Promise<TokenResponse>,
        fetch("/api/config").then((r) => r.json()) as Promise<ServerConfig>,
        fetch("/api/session").then((r) => r.json()).catch(() => null) as Promise<SessionState | null>,
      ]);

      // Use stored handle for session resumption if available
      if (sessionRes?.gemini_handle) {
        this.sessionHandle = sessionRes.gemini_handle;
      }

      const ai = new GoogleGenAI({
        apiKey: tokenRes.token,
        httpOptions: { apiVersion: "v1alpha" },
      });

      log("GEMINI", `Connecting model=${configRes.model} token_len=${tokenRes.token.length} prompt_len=${configRes.system_prompt.length} tools=${functionDeclarations.map(f => f.name).join(",")}`);
      log("GEMINI", `Tool declarations: ${JSON.stringify(functionDeclarations.map(f => ({ name: f.name, params: Object.keys((f.parametersJsonSchema as any)?.properties || {}) })))}`);

      // Determine if we are in always-on mode
      this.isAlwaysOn = this.audioManager.getMode() === "always-on";
      this.wakeWordEnabled = this.isAlwaysOn;
      if (this.wakeWordEnabled) {
        this.awake = false;
        setTimeout(() => this.callbacks.onStandbyMode?.(), 500);
      }

      // Wire up audio capture — in always-on mode audio flows continuously
      // and Gemini uses AUTOMATIC activity detection (no manual VAD signals)
      this.audioManager.clearListeners();
      this.audioManager.setOnCaptureStart(() => {
        // In always-on: no-op, Gemini auto-detects speech via AAD
        // In manual modes: tell Gemini user started talking
        if (!this.isAlwaysOn) {
          this.sendActivityStart();
        }
      });
      this.audioManager.setOnCaptureEnd(() => {
        if (!this.isAlwaysOn) {
          this.sendActivityEnd();
        }
      });

      this.audioManager.setOnChunk((base64) => {
        this.sendAudio(base64);
      });

      this.audioManager.setOnPlaybackEnded(() => {
        if (this.wakeWordEnabled && this.awake) {
          log("WAKEWORD", "J.A.R.V.I.S. terminou de falar. Mudando para idle e iniciando janela de 5s de escuta.");
          this.setConnectionState("idle");
          this.startWakeTimeout();
        }
      });


      log("GEMINI", "Connection handshake started...");
      this.session = await ai.live.connect({
        model: configRes.model,
        config: {
          responseModalities: [Modality.AUDIO],
          systemInstruction: configRes.system_prompt,
          tools: [{ functionDeclarations }],
          speechConfig: {
            languageCode: this.languageCode,
            voiceConfig: {
              prebuiltVoiceConfig: { voiceName: "Puck" },
            },
          },
          outputAudioTranscription: {},
          inputAudioTranscription: {},
          realtimeInputConfig: this.isAlwaysOn
            ? {
                // ALWAYS-ON: Gemini detecta silêncio automaticamente (AAD)
                automaticActivityDetection: {
                  // silenceDurationMs: ms de silêncio até fechar o turno e responder
                  silenceDurationMs: 800,
                  // HIGH = detecta fim de fala mais rapidamente (menos espera)
                  endOfSpeechSensitivity: "END_SENSITIVITY_HIGH" as any,
                  startOfSpeechSensitivity: "START_SENSITIVITY_HIGH" as any,
                },
              }
            : {
                // MANUAL modes (PTT/Toggle): desativa AAD, usa activityStart/End manuais
                automaticActivityDetection: { disabled: true },
              },
          sessionResumption: {
            ...(this.sessionHandle ? { handle: this.sessionHandle } : {}),
          },
          thinkingConfig: {
            thinkingLevel: "high" as any,
          },
          contextWindowCompression: {
            slidingWindow: {},
          },
        },
        callbacks: {
          onopen: () => {
            log("GEMINI", "Connected");
            this.callbacks.onConnected();
          },
          onmessage: (message: any) => {
            logGeminiMessage(message);
            this.handleMessage(message);
          },
          onerror: (error: any) => {
            log("GEMINI", "Error", error?.message || error);
          },
          onclose: (event: any) => {
            log("GEMINI", "Disconnected", `code=${event?.code} reason=${event?.reason || "unknown"} wasClean=${event?.wasClean}`);

            // Don't reconnect if closed intentionally
            if (this.intentionallyClosed) {
              log("GEMINI", "Closed intentionally, skipping reconnect");
              return;
            }

            // Clear stale session handle on "session not found" to avoid reconnect loop
            if (event?.code === 1008) {
              this.sessionHandle = null;
              fetch("/api/session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ gemini_handle: null }),
              }).catch(() => {});
            }
            this.callbacks.onDisconnected();
            this.scheduleReconnect();
          },
        },
      });
    } catch (err) {
      console.error("Gemini connection failed:", err);
      this.callbacks.onDisconnected();
      this.scheduleReconnect();
    }
  }

  private handleMessage(message: any): void {
    // Session resumption updates — store the handle
    if (message.sessionResumptionUpdate) {
      const update = message.sessionResumptionUpdate;
      if (update.resumable && update.newHandle) {
        this.sessionHandle = update.newHandle;
        // Persist handle to backend
        fetch("/api/session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gemini_handle: this.sessionHandle }),
        }).catch(() => {});
      }
    }

    // Model turn parts — audio, thought, text
    if (message.serverContent?.modelTurn?.parts) {
      if (this.wakeWordEnabled && !this.awake) {
        return;
      }
      this.cancelWakeTimeout();
      for (const part of message.serverContent.modelTurn.parts) {
        // Audio data — from inlineData (NOT message.data which crashes on thought messages)
        if (part.inlineData?.data) {
          this.setConnectionState("speaking");
          this.audioManager.queuePlayback(part.inlineData.data);
        } else if (part.thought) {
          // Thought = internal reasoning
          this.setConnectionState("thinking");
          if (part.text) {
            this.callbacks.onThinking(part.text);
          }
        } else if (part.text) {
          // Regular text response (non-audio)
          this.callbacks.onTranscript("gemini", part.text);
        }
      }
    }

    // Input transcription — show as draft, will be replaced by accurate STT
    if (message.serverContent?.inputTranscription?.text) {
      const text = message.serverContent.inputTranscription.text;
      if (this.wakeWordEnabled && !this.awake) {
        const transcript = text.toLowerCase();
        if (transcript.includes("jarvis")) {
          this.awake = true;
          log("WAKEWORD", "Wake word 'Jarvis' detected!");
          this.callbacks.onWakeWordDetected?.();
          const cleanText = text.replace(/^[Jj]arvis[,\s]*/i, "");
          this.callbacks.onTranscript("user", cleanText || "Jarvis");
        } else {
          return;
        }
      } else {
        this.cancelWakeTimeout();
        this.callbacks.onTranscript("user", text);
      }
    }

    // Output audio transcription (what Gemini said)
    if (message.serverContent?.outputTranscription?.text) {
      if (this.wakeWordEnabled && !this.awake) return;
      this.cancelWakeTimeout();
      this.callbacks.onTranscript(
        "gemini",
        message.serverContent.outputTranscription.text
      );
    }

    // Interrupted — user spoke over Gemini, stop playback immediately
    if (message.serverContent?.interrupted) {
      log("GEMINI", "Interrupted by user");
      this.audioManager.clearPlayback();
      this.callbacks.onInterrupted();
      this.setConnectionState("idle");
      this.cancelWakeTimeout();
    }

    // Turn complete — back to idle, end transcript accumulation
    if (message.serverContent?.turnComplete) {
      this.callbacks.onTurnComplete();
      if (this.wakeWordEnabled) {
        if (this.audioManager.isSpeaking()) {
          log("WAKEWORD", "TurnComplete recebido, mas J.A.R.V.I.S. ainda está falando. Mantendo estado 'speaking'.");
        } else {
          this.setConnectionState("idle");
          this.startWakeTimeout();
        }
      } else {
        this.setConnectionState("idle");
      }
    }

    // Function calls — forward to backend
    if (message.toolCall?.functionCalls) {
      if (this.wakeWordEnabled && !this.awake) return;
      this.cancelWakeTimeout();
      for (const call of message.toolCall.functionCalls) {
        log("GEMINI", `Function call: ${call.name}`, call.args);
        this.callbacks.onFunctionCall(call.id, call.name, call.args || {});
      }
    }
  }

  private audioSendCount = 0;

  sendAudio(base64Pcm: string): void {
    if (!this.session) {
      log("AUDIO_SEND", "No session, skipping");
      return;
    }

    const rms = getAudioVolumeRMS(base64Pcm);

    if (this.wakeWordEnabled && this.awake) {
      if (this.audioManager.isSpeaking() || this.currentState === "speaking") {
        // J.A.R.V.I.S. está falando: cancela o standby para não desativar no meio da fala dele
        this.cancelWakeTimeout();
      } else if (rms > 500) {
        // Usuário está falando: cancela o timeout de inatividade para mantê-lo ouvindo
        this.cancelWakeTimeout();
      } else {
        // Usuário está em silêncio: se o timer não estiver rodando e o Gemini estiver em escuta/ocioso
        if (this.wakeTimeout === null && (this.currentState === "idle" || this.currentState === "listening")) {
          this.startWakeTimeout();
        }
      }
    }

    try {
      this.session.sendRealtimeInput({
        audio: {
          data: base64Pcm,
          mimeType: "audio/pcm;rate=16000",
        },
      });
      this.audioSendCount++;
      if (this.audioSendCount % 50 === 1) {
        log("AUDIO_SEND", `Sent chunk #${this.audioSendCount} to Gemini (${base64Pcm.length} chars) | RMS=${rms.toFixed(1)}`);
      }
    } catch (err) {
      log("AUDIO_SEND", `ERROR sending audio: ${err}`);
    }
  }

  /** Send a text message to Gemini, optionally with images. */
  sendText(text: string, images?: { mimeType: string; data: string }[]): void {
    if (!this.session) return;
    try {
      const parts: any[] = [];

      if (images && images.length > 0) {
        for (const img of images) {
          parts.push({ inlineData: { mimeType: img.mimeType, data: img.data } });
        }
        if (text) parts.push({ text });
        
        log("GEMINI", `Sending ${images.length} image(s) via sendClientContent`);
        this.session.sendClientContent({
          turns: [{ role: "user", parts }],
          turnComplete: true,
        });
      } else if (text) {
        // For pure text, sendRealtimeInput is more robust in Flash Live.
        // In always-on mode, we do NOT wrap in activityStart/End because
        // the SDK handles AAD automatically.
        if (!this.isAlwaysOn) {
          this.sendActivityStart();
        }
        this.session.sendRealtimeInput({ text });
        if (!this.isAlwaysOn) {
          this.sendActivityEnd();
        }
        log("GEMINI", `Sent text message via sendRealtimeInput: "${text}"`);
      }
    } catch (err) {
      log("GEMINI", `ERROR sending message: ${err}`);
    }
  }

  /** Signal that the user stopped speaking (spacebar released / toggle off). */
  sendAudioEnd(): void {
    if (!this.session) return;
    try {
      this.session.sendRealtimeInput({ audioStreamEnd: true });
      log("AUDIO_SEND", `Sent audioStreamEnd after ${this.audioSendCount} chunks`);
      this.audioSendCount = 0;
    } catch (err) {
      log("AUDIO_SEND", `ERROR sending audioStreamEnd: ${err}`);
    }
  }

  /** Tell Gemini user started talking — suppresses automatic VAD turn detection. */
  sendActivityStart(): void {
    if (!this.session) return;
    try {
      this.session.sendRealtimeInput({ activityStart: {} });
      log("AUDIO_SEND", "Sent activityStart (manual VAD)");
    } catch (err) {
      log("AUDIO_SEND", `ERROR sending activityStart: ${err}`);
    }
  }

  /** Tell Gemini user finished talking — signals end of turn. */
  sendActivityEnd(): void {
    if (!this.session) return;
    try {
      this.session.sendRealtimeInput({ activityEnd: {} });
      log("AUDIO_SEND", "Sent activityEnd (manual VAD)");
    } catch (err) {
      log("AUDIO_SEND", `ERROR sending activityEnd: ${err}`);
    }
  }

  sendFunctionResponse(id: string, name: string, result: string): void {
    if (!this.session) return;
    try {
      this.session.sendToolResponse({
        functionResponses: [
          {
            id,
            name,
            response: { result },
          },
        ],
      });
    } catch (err) {
      console.error("Failed to send function response:", err);
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnecting) return;
    this.reconnecting = true;
    console.log("Reconnecting to Gemini in 3s...");
    setTimeout(async () => {
      this.reconnecting = false;
      await this.connect();
    }, 3000);
  }

  clearSessionHandle(): void {
    this.sessionHandle = null;
  }

  async disconnect(): Promise<void> {
    this.intentionallyClosed = true;
    this.reconnecting = true; // Prevent auto-reconnect
    this.cancelWakeTimeout();
    if (this.session) {
      try {
        this.session.close();
      } catch {
        // Already closed
      }
      this.session = null;
    }
  }

  private startWakeTimeout(): void {
    this.cancelWakeTimeout();
    if (!this.wakeWordEnabled) return;

    if (this.audioManager.isSpeaking() || this.currentState === "speaking") {
      log("WAKEWORD", "startWakeTimeout cancelado pois J.A.R.V.I.S. está falando.");
      return;
    }

    log("WAKEWORD", `Agendando standby em ${this.WAKE_TIMEOUT_MS / 1000}s`);
    this.wakeTimeout = setTimeout(() => {
      this.awake = false;
      this.callbacks.onStandbyMode?.();
      log("WAKEWORD", "Standby ativado devido a inatividade");
    }, this.WAKE_TIMEOUT_MS) as any;
  }

  private cancelWakeTimeout(): void {
    if (this.wakeTimeout) {
      clearTimeout(this.wakeTimeout);
      this.wakeTimeout = null;
    }
  }

  private setConnectionState(state: "idle" | "thinking" | "speaking" | "listening"): void {
    this.currentState = state;
    this.callbacks.onStateChange(state);
  }
}

/** Calcula a energia RMS do chunk de áudio PCM de 16-bit em base64. */
function getAudioVolumeRMS(base64: string): number {
  try {
    const binary = atob(base64);
    const len = binary.length;
    let sum = 0;
    const numSamples = len / 2;
    if (numSamples === 0) return 0;
    
    for (let i = 0; i < len; i += 2) {
      let sample = binary.charCodeAt(i) | (binary.charCodeAt(i + 1) << 8);
      if (sample >= 32768) sample -= 65536;
      sum += sample * sample;
    }
    return Math.sqrt(sum / numSamples);
  } catch {
    return 0;
  }
}
