"""LLM router — every agent runs on an open-weight model through an
OpenAI-compatible provider.

Providers are tried in settings.provider_order (default: groq, then
huggingface). Groq is first because its free tier is generous and it is the
fastest; HuggingFace takes over once Groq's daily budget is spent. If a
provider is out of quota or rate-limited, the router moves to the next one
rather than failing the agent.

Agents are grouped into three tiers, and each provider maps its own model to
each tier (see config). Override any of them with an env var — no code change.
  reasoning — judgment calls: bid/no-bid, QA gate, MD briefing
  analysis  — long structured tables: legal, technical, finance, pricing
  general   — research, logistics, HR, document control
"""
import asyncio
import threading
import time
import random
import urllib.request
from openai import (
    OpenAI,
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
)
from app.core.config import settings


# === agent_id → tier ===
AGENT_TIER: dict[str, str] = {
    # --- Bid Pipeline ---
    "bid-manager":         "reasoning",
    "qa-reviewer":         "reasoning",

    "legal-compliance":    "analysis",
    "technical-expert":    "analysis",
    "finance-accounts":    "analysis",
    "bid-pricing":         "analysis",
    "tender-brief":        "analysis",

    "market-intelligence": "general",
    "govt-relations":      "general",
    "technical-writer":    "general",
    "doc-controller":      "general",
    "admin-hr":            "general",
    "it-support":          "general",

    # --- Roadmap Analysis phases ---
    "md-final":            "reasoning",
    "phase-6-win":         "reasoning",
    "phase-3-build":       "analysis",
    "phase-2-qualify":     "analysis",
    "phase-1-hunt":        "general",
    "phase-4-review":      "general",
    "phase-5-submit":      "general",
    "phase-7-execute":     "general",
}

NO_PROVIDER_MESSAGE = (
    "No LLM provider is configured. Set at least one of: OPENROUTER_API_KEY "
    "(free, https://openrouter.ai/keys), GROQ_API_KEY (free, "
    "https://console.groq.com/keys), or HF_TOKEN "
    "(https://huggingface.co/settings/tokens)."
)

ALL_EXHAUSTED_MESSAGE = (
    "Every configured LLM provider reported exhausted credits or quota. "
    "Check the billing or usage limits of the providers listed below."
)


class AICancelled(Exception):
    """The caller stopped the request (e.g. the user pressed Stop analysis)."""


AI_UNAVAILABLE_MESSAGE = (
    "The AI service is temporarily unavailable. Please press Retry in a few minutes."
)


def user_facing_error(err: BaseException) -> str:
    """Short message for customers; provider internals stay in the server log."""
    text = str(err)
    if isinstance(err, TimeoutError) or "Timed out" in text:
        return "This step took too long to finish. Please press Retry."
    if text.startswith(("All providers failed", ALL_EXHAUSTED_MESSAGE, NO_PROVIDER_MESSAGE)):
        return AI_UNAVAILABLE_MESSAGE
    return text


def _pause(seconds: float, cancel: threading.Event | None) -> None:
    """Back off between attempts; wakes immediately when cancelled."""
    if cancel is None:
        time.sleep(seconds)
    elif cancel.wait(seconds):
        raise AICancelled()


def tier_for(agent_id: str | None) -> str:
    return AGENT_TIER.get(agent_id or "", "general")


def model_for(agent_id: str | None, provider: str) -> str:
    return settings.models_for(provider)[tier_for(agent_id)]


_clients: dict[str, OpenAI] = {}

# OLLAMA_BASE_URL may list several GPU servers, comma-separated, in order of
# preference (main server first, then backups). Only one is normally on; the
# first that answers is used, and the choice is rechecked every minute.
_OLLAMA_RECHECK_S = 60.0
_ollama_pick: tuple[float, str] | None = None
_ollama_lock = threading.Lock()


def _ollama_reachable(base_url: str) -> bool:
    root = base_url.rstrip("/").removesuffix("/v1")
    try:
        with urllib.request.urlopen(root + "/api/tags", timeout=2):
            return True
    except Exception:
        return False


def _ollama_base_url() -> str:
    global _ollama_pick
    urls = [u.strip() for u in settings.ollama_base_url.split(",") if u.strip()]
    if len(urls) <= 1:
        return urls[0] if urls else settings.ollama_base_url
    with _ollama_lock:
        now = time.monotonic()
        if _ollama_pick and now - _ollama_pick[0] < _OLLAMA_RECHECK_S:
            return _ollama_pick[1]
        url = next((u for u in urls if _ollama_reachable(u)), urls[0])
        _ollama_pick = (now, url)
        return url


def _client_for(provider: str) -> OpenAI:
    api_key, base_url = settings.credentials_for(provider)
    if provider == "ollama":
        base_url = _ollama_base_url()
    key = f"{provider}|{base_url}"
    if key not in _clients:
        headers = None
        if provider == "openrouter":
            # OpenRouter attributes traffic to the app via these headers.
            headers = {"HTTP-Referer": settings.app_url, "X-Title": settings.app_name}
        _clients[key] = OpenAI(
            api_key=api_key, base_url=base_url,
            timeout=1800.0 if provider in ("ollama", "ik_llama") else 300.0,
            max_retries=0 if provider in ("ollama", "ik_llama") else 2,
            default_headers=headers
        )
    return _clients[key]


def _is_quota_exhausted(err: Exception) -> bool:
    """Out of credits or past a hard daily cap — another attempt on this
    provider will not help."""
    if isinstance(err, APIStatusError) and err.status_code == 402:
        return True
    msg = str(err).lower()
    return any(s in msg for s in (
        "depleted your monthly included credits",
        "exceeded your monthly included credits",
        "insufficient credits",
        "quota exceeded",
        "payment required",
        "credit balance",
        "requests per day",
        "tokens per day",
    ))


def _model_unavailable(err: Exception) -> bool:
    """This provider doesn't serve this model (bad id, provider down)."""
    if isinstance(err, APIStatusError) and err.status_code in (400, 404):
        return True
    msg = str(err).lower()
    return any(s in msg for s in (
        "not supported",
        "no provider",
        "model not found",
        "does not exist",
        "decommissioned",
    ))


def _no_think_params(provider: str, model: str) -> dict:
    """Newer Ollama releases ignore the /no_think prompt hint and spend the token
    budget on a hidden reasoning trace (empty replies, slow analyses). The
    OpenAI-compatible reasoning_effort switch turns thinking off reliably."""
    if provider == "ollama" and model.lower().startswith("qwen3"):
        return {"extra_body": {"reasoning_effort": "none"}}
    return {}


def _call(provider: str, model: str, system_prompt: str, messages: list[dict], max_tokens: int,
          cancel: threading.Event | None = None) -> str:
    request_messages = [{"role": "system", "content": system_prompt}, *messages]
    if provider in ("ollama", "ik_llama") and model.lower().startswith("qwen3"):
        # Qwen3 defaults to a long thinking trace. Local CPU runs are much
        # faster and return usable content reliably when thinking is disabled.
        request_messages = [dict(message) for message in request_messages]
        for message in reversed(request_messages):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                message["content"] += "\n\n/no_think"
                break
    if cancel is not None:
        return _call_streaming(provider, model, request_messages, max_tokens, cancel)
    response = _client_for(provider).chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        # Tender decisions should be reproducible. A low temperature reduces
        # drift between repeated analyses of the same evidence.
        temperature=0.1,
        messages=request_messages,
        **_no_think_params(provider, model),
    )
    choices = getattr(response, "choices", None)
    if not choices:
        # Some OpenAI-compatible providers occasionally return a successful
        # HTTP response with a missing/null choices array. Treat that as a
        # provider failure so chat() can fall through to the next provider.
        raise RuntimeError(f"[{provider}:{model}] provider returned no choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"[{provider}:{model}] provider returned empty content")
    return content


def _call_streaming(provider: str, model: str, request_messages: list[dict], max_tokens: int,
                    cancel: threading.Event) -> str:
    """Stream the reply so a cancel can close the connection mid-generation.

    Closing the stream makes the inference server stop generating, which frees
    the GPU for the next request instead of finishing an answer nobody reads.
    """
    stream = _client_for(provider).chat.completions.create(
        model=model, max_tokens=max_tokens, temperature=0.1,
        messages=request_messages, stream=True,
        **_no_think_params(provider, model),
    )
    parts: list[str] = []
    try:
        for chunk in stream:
            if cancel.is_set():
                raise AICancelled()
            for choice in chunk.choices or []:
                piece = getattr(choice.delta, "content", None)
                if piece:
                    parts.append(piece)
    finally:
        stream.close()
    content = "".join(parts)
    if not content.strip():
        raise RuntimeError(f"[{provider}:{model}] provider returned empty content")
    return content


def _try_provider(provider: str, system_prompt: str, messages: list[dict], max_tokens: int, agent_id: str | None,
                  cancel: threading.Event | None = None) -> str:
    """Run the agent on one provider, retrying transient failures.

    Raises RateLimitError/APIStatusError up to the caller when this provider is
    exhausted, so the caller can move to the next one.
    """
    model = model_for(agent_id, provider)
    fallback = settings.models_for(provider)["general"]
    tried_fallback = False

    last_err: Exception | None = None
    for attempt in range(4):
        if cancel is not None and cancel.is_set():
            raise AICancelled()
        try:
            return _call(provider, model, system_prompt, messages, max_tokens, cancel)
        except (RateLimitError, APIStatusError) as e:
            last_err = e
            if _is_quota_exhausted(e):
                raise
            # Model not served here — drop to this provider's general model once.
            if _model_unavailable(e) and not tried_fallback and model != fallback:
                model, tried_fallback = fallback, True
                continue
            if isinstance(e, APIStatusError) and e.status_code and e.status_code < 500 and e.status_code not in (408, 429):
                raise
            _pause((2 ** attempt) + random.uniform(0, 1), cancel)
        except (APIConnectionError, APITimeoutError) as e:
            last_err = e
            _pause((2 ** attempt) + random.uniform(0, 1), cancel)
        except RuntimeError as e:
            # OpenAI-compatible inference endpoints can occasionally return
            # HTTP 200 with no choices/content while a model worker is under
            # load. That response is transient, so retry it on the same
            # provider before falling through to a fallback provider.
            last_err = e
            if "provider returned no choices" not in str(e) and "provider returned empty content" not in str(e):
                raise
            _pause((2 ** attempt) + random.uniform(0, 1), cancel)

    raise RuntimeError(f"[{provider}:{model}] failed after 4 attempts: {last_err}")


def vision_chat(prompt: str, image_b64: str, max_tokens: int = 4000) -> str:
    """Transcribe an image with a vision-capable model.

    Used to read scanned tenders that have no text layer. Runs on each
    provider's dedicated vision model — the general-tier models are text-only
    and reject images outright — and falls through providers like chat().
    """
    providers = settings.configured_providers()
    if not providers:
        raise RuntimeError(NO_PROVIDER_MESSAGE)

    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
    ]

    errors: list[str] = []
    for provider in providers:
        model = settings.models_for(provider)["vision"]
        if not model:
            errors.append(f"{provider}: no vision model configured. Use a text-based PDF or DOCX, or configure OLLAMA_VISION_MODEL with an installed vision model.")
            continue
        try:
            response = _client_for(provider).chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0.1,  # transcription, not creativity
                messages=[{"role": "user", "content": content}],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            errors.append(f"{provider}: {str(e)[:120]}")
            continue

    raise RuntimeError("Vision transcription failed. " + " | ".join(errors))


def chat(system_prompt: str, messages: list[dict], max_tokens: int | None = None, agent_id: str | None = None,
         cancel: threading.Event | None = None) -> str:
    """Run this agent's turn, falling through providers until one succeeds."""
    if max_tokens is None:
        max_tokens = settings.max_tokens

    providers = settings.configured_providers()
    if not providers:
        raise RuntimeError(NO_PROVIDER_MESSAGE)

    errors: list[str] = []
    exhausted: list[bool] = []
    for provider in providers:
        try:
            return _try_provider(provider, system_prompt, messages, max_tokens, agent_id, cancel)
        except (RateLimitError, APIStatusError) as e:
            errors.append(f"{provider}: {str(e)[:600]}")
            exhausted.append(_is_quota_exhausted(e))
            continue  # exhausted or rejected here — try the next provider
        except RuntimeError as e:
            errors.append(f"{provider}: {str(e)[:600]}")
            exhausted.append(_is_quota_exhausted(e))
            continue

    if exhausted and all(exhausted):
        raise RuntimeError(ALL_EXHAUSTED_MESSAGE + " " + " | ".join(errors))
    raise RuntimeError("All providers failed. " + " | ".join(errors))


async def chat_async(system_prompt: str, messages: list[dict], max_tokens: int | None = None,
                     agent_id: str | None = None) -> str:
    """chat() in a worker thread that stops when the awaiting task is cancelled.

    Cancelling an asyncio task does not stop the thread it is waiting on, so a
    stopped analysis used to keep retrying and generating on the shared GPU.
    The event reaches into the thread: pending retries are skipped and the
    in-flight stream is closed.
    """
    cancel = threading.Event()
    try:
        return await asyncio.to_thread(
            chat, system_prompt=system_prompt, messages=messages,
            max_tokens=max_tokens, agent_id=agent_id, cancel=cancel,
        )
    except asyncio.CancelledError:
        cancel.set()
        raise
