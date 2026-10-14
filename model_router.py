"""Catálogo de modelos e roteamento entre eles.

Cada tarefa tem um nível (rapido / padrao / forte). O roteador monta uma lista
ordenada de modelos candidatos para o nível, pulando os que estão sem cota,
fora do ar ou desligados, e aprende com cada chamada:

- 429 (cota)            → modelo em espera pelo tempo que a API pedir (ou 60 s);
                          cota zero ("limit: 0") → espera de 1 h.
- 500/503 (sobrecarga)  → espera de 30 s.
- 404/410 (não existe)  → desligado até reiniciar o servidor.
- sucesso               → latência entra na média móvel usada para ordenar.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

TIERS = ("rapido", "padrao", "forte")

TIER_LABELS = {
    "rapido": "Rápido",
    "padrao": "Padrão",
    "forte": "Forte",
}


@dataclass(frozen=True)
class ModelSpec:
    id: str          # id completo com provedor, ex.: "google/gemini-flash-latest"
    provider: str    # google | nvidia | openrouter
    model: str       # id enviado à API do provedor
    label: str
    tier: str


CATALOG: list[ModelSpec] = [
    # Rápido: respostas curtas, leitura, status, comandos simples
    ModelSpec("google/gemini-flash-lite-latest", "google", "gemini-flash-lite-latest", "Gemini Flash Lite", "rapido"),
    ModelSpec("google/gemini-3.5-flash-lite", "google", "gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", "rapido"),
    ModelSpec("nvidia/nvidia/nemotron-3-super-120b-a12b", "nvidia", "nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super", "rapido"),
    # Padrão: codificar, corrigir bugs
    ModelSpec("google/gemini-flash-latest", "google", "gemini-flash-latest", "Gemini Flash", "padrao"),
    ModelSpec("google/gemini-3.8-flash", "google", "gemini-3.8-flash", "Gemini 3.8 Flash", "padrao"),
    ModelSpec("google/gemini-3.5-flash", "google", "gemini-3.5-flash", "Gemini 3.5 Flash", "padrao"),
    ModelSpec("nvidia/z-ai/glm-5.3", "nvidia", "z-ai/glm-5.3", "GLM 5.3", "padrao"),
    ModelSpec("nvidia/deepseek-ai/deepseek-v4.1-flash", "nvidia", "deepseek-ai/deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "padrao"),
    # Forte: planejar, revisar, investigar, subagentes
    ModelSpec("google/gemini-pro-latest", "google", "gemini-pro-latest", "Gemini Pro", "forte"),
    ModelSpec("google/gemini-3.1-pro-preview", "google", "gemini-3.1-pro-preview", "Gemini 3.1 Pro", "forte"),
    ModelSpec("nvidia/moonshotai/kimi-k3", "nvidia", "moonshotai/kimi-k3", "Kimi K3", "forte"),
    # OpenRouter (só aparecem com OPENROUTER_API_KEY)
    ModelSpec("openrouter/anthropic/claude-sonnet-4.5", "openrouter", "anthropic/claude-sonnet-4.5", "Claude Sonnet (OpenRouter)", "forte"),
    ModelSpec("openrouter/deepseek/deepseek-chat", "openrouter", "deepseek/deepseek-chat", "DeepSeek Chat (OpenRouter)", "padrao"),
]

# Nível de cada tipo de tarefa (nomes das funções chamadas pela voz)
TASK_TIERS = {
    "code_task": "padrao",
    "debug_issue": "padrao",
    "write_file": "padrao",
    "save_canvas_file": "padrao",
    "computer_control": "padrao",
    "plan_task": "forte",
    "investigate_and_advise": "forte",
    "review_changes": "forte",
    "delegate_to_programmer": "forte",
    "delegate_to_designer": "forte",
    "read_file": "rapido",
    "get_status": "rapido",
    "run_command": "rapido",
    "list_directory": "rapido",
    "create_directory": "rapido",
    "launch_app": "rapido",
    "open_url": "rapido",
    "open_app": "rapido",
    "manage_background_task": "rapido",
}

# Ordem de níveis de reserva quando todos os modelos do nível pedido falham
TIER_FALLBACK = {
    "rapido": ("rapido", "padrao", "forte"),
    "padrao": ("padrao", "forte", "rapido"),
    "forte": ("forte", "padrao", "rapido"),
}

EFFORT_SHIFT = {"low": -1, "medium": 0, "high": 0, "max": 1}

COOLDOWN_QUOTA = 60
COOLDOWN_QUOTA_ZERO = 3600
COOLDOWN_OVERLOAD = 30


@dataclass
class ModelHealth:
    cooldown_until: float = 0.0
    disabled: str | None = None
    last_error: str | None = None
    latency: float | None = None   # média móvel em segundos
    ok: int = 0
    fail: int = 0
    last_used: float = 0.0
    extra: dict = field(default_factory=dict)


class AllModelsFailed(Exception):
    pass


class ModelRouter:
    def __init__(self, providers: dict[str, bool]):
        self.providers = providers
        self.health: dict[str, ModelHealth] = {m.id: ModelHealth() for m in CATALOG}
        self.last_choice: dict | None = None

    # ── consulta ───────────────────────────────────────────────

    def models(self) -> list[ModelSpec]:
        return [m for m in CATALOG if self.providers.get(m.provider)]

    def get(self, model_id: str) -> ModelSpec | None:
        model_id = normalize_model_id(model_id)
        return next((m for m in CATALOG if m.id == model_id), None)

    def is_available(self, model_id: str) -> bool:
        h = self.health.get(model_id)
        if h is None:
            return True
        return not h.disabled and h.cooldown_until <= time.time()

    def plan(self, task_kind: str | None, pinned: str | None = None, effort: str = "high") -> tuple[str, list[ModelSpec]]:
        """Retorna (nível, candidatos em ordem). Modelo fixado vai primeiro."""
        tier = shift_tier(TASK_TIERS.get(task_kind or "", "padrao"), EFFORT_SHIFT.get(effort or "high", 0))
        ordered: list[ModelSpec] = []

        pinned_spec = self.get(pinned) if pinned and pinned != "auto" else None
        if pinned_spec and self.providers.get(pinned_spec.provider):
            ordered.append(pinned_spec)

        for t in TIER_FALLBACK[tier]:
            same_tier = [m for m in self.models() if m.tier == t and m not in ordered]
            ordered += sorted(same_tier, key=self._rank)

        available = [m for m in ordered if self.is_available(m.id)]
        # Se tudo estiver em espera, tenta mesmo assim pelo que libera primeiro
        if not available:
            available = sorted(
                [m for m in ordered if not self.health[m.id].disabled],
                key=lambda m: self.health[m.id].cooldown_until,
            )
        return tier, available

    def _rank(self, m: ModelSpec):
        h = self.health[m.id]
        # Modelos ainda não medidos ficam no meio; Google antes no empate (voz já usa a mesma chave)
        latency = h.latency if h.latency is not None else 8.0
        failure_ratio = h.fail / (h.ok + h.fail) if (h.ok + h.fail) else 0.0
        return (latency * (1 + 2 * failure_ratio), 0 if m.provider == "google" else 1)

    # ── aprendizado ────────────────────────────────────────────

    def report_success(self, model_id: str, latency: float, tier: str | None = None, task_kind: str | None = None):
        h = self.health.setdefault(model_id, ModelHealth())
        h.ok += 1
        h.last_error = None
        h.last_used = time.time()
        h.latency = latency if h.latency is None else 0.7 * h.latency + 0.3 * latency
        self.last_choice = {"model": model_id, "tier": tier, "task": task_kind, "latency": round(latency, 1), "at": time.time()}

    def report_failure(self, model_id: str, error: str) -> str:
        """Registra a falha e devolve um resumo curto do motivo."""
        h = self.health.setdefault(model_id, ModelHealth())
        h.fail += 1
        h.last_used = time.time()
        err = error or ""
        code = _status_code(err)

        if code in (404, 410) or "not found" in err.lower() and code is None:
            h.disabled = "indisponível nesta chave"
            reason = h.disabled
        elif code == 429 or "resource_exhausted" in err.lower() or "quota" in err.lower():
            if re.search(r"limit['\"]?\s*:\s*0\b", err) or "limit: 0" in err:
                wait = COOLDOWN_QUOTA_ZERO
                reason = "sem cota nesta chave"
            else:
                wait = _retry_delay(err) or COOLDOWN_QUOTA
                reason = f"cota esgotada, espera {int(wait)}s"
            h.cooldown_until = time.time() + wait
        elif code in (500, 502, 503, 504) or "unavailable" in err.lower() or "overloaded" in err.lower() or "timed out" in err.lower() or "timeout" in err.lower():
            h.cooldown_until = time.time() + COOLDOWN_OVERLOAD
            reason = "sobrecarregado"
        else:
            reason = "erro"
        h.last_error = f"{reason}: {err[:160]}"
        return reason

    def snapshot(self) -> dict:
        now = time.time()
        rows = []
        for m in self.models():
            h = self.health[m.id]
            if h.disabled:
                state = "off"
            elif h.cooldown_until > now:
                state = "wait"
            elif h.ok:
                state = "ok"
            else:
                state = "idle"
            rows.append({
                "id": m.id, "label": m.label, "provider": m.provider, "tier": m.tier,
                "state": state,
                "wait": max(0, int(h.cooldown_until - now)),
                "latency": round(h.latency, 1) if h.latency is not None else None,
                "ok": h.ok, "fail": h.fail,
                "error": h.last_error,
            })
        return {"models": rows, "last": self.last_choice, "tiers": TIER_LABELS}


def normalize_model_id(model_id: str) -> str:
    """Aceita ids antigos ('models/x', 'x', 'google/x') e devolve o id do catálogo."""
    m = (model_id or "").strip()
    if not m or m == "auto":
        return m
    m = m.replace("models/", "")
    if m.startswith(("google/", "nvidia/", "openrouter/")):
        return m
    if "gemini" in m:
        return f"google/{m}"
    return m


def shift_tier(tier: str, delta: int) -> str:
    i = TIERS.index(tier) if tier in TIERS else 1
    return TIERS[max(0, min(len(TIERS) - 1, i + delta))]


def _status_code(err: str) -> int | None:
    m = re.search(r"\b(4\d\d|5\d\d)\b", err)
    return int(m.group(1)) if m else None


def _retry_delay(err: str) -> float | None:
    m = re.search(r"retry(?:Delay)?['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", err, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", err, re.IGNORECASE)
    return float(m.group(1)) if m else None
