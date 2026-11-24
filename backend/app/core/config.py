import os
from pathlib import Path
from dotenv import load_dotenv

_env_file = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=_env_file, override=True)


class Settings:
    """Agents run on open-weight models through OpenAI-compatible providers.

    Providers are tried in PROVIDER_ORDER; when one is rate-limited or out of
    quota the router falls through to the next, so a single provider having a
    bad day never fails an analysis.

      openrouter  — free tier, 1M-context models, no cost per token
      groq        — free tier, fastest inference
      huggingface — paid fallback, widest model choice

    Configure any subset. Only providers with a key are used.
    """

    provider_order: list[str] = [
        p.strip()
        for p in os.getenv("PROVIDER_ORDER", "openrouter,groq,huggingface").split(",")
        if p.strip()
    ]

    # === OpenRouter — free models (ids ending in :free cost nothing) ===
    # https://openrouter.ai/keys — free signup, no card.
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    # Verified live on the public catalog: 1M context / 65k max output.
    # Ultra-550B produces good work but takes ~220s per agent, which put a full
    # analysis over 30 minutes. Super-120B is materially faster at comparable
    # quality on these prompts, so it carries both heavy tiers.
    openrouter_model_reasoning: str = os.getenv(
        "OPENROUTER_MODEL_REASONING", "nvidia/nemotron-3-super-120b-a12b:free"
    )
    openrouter_model_analysis: str = os.getenv(
        "OPENROUTER_MODEL_ANALYSIS", "nvidia/nemotron-3-super-120b-a12b:free"
    )
    # gemma-4-31b is popular enough on the free tier to rate-limit under load;
    # the nano is far less contended and fine for the lighter agents.
    openrouter_model_general: str = os.getenv(
        "OPENROUTER_MODEL_GENERAL", "nvidia/nemotron-3-nano-30b-a3b:free"
    )
    # Must accept images — used to read scanned tenders. Verified against the
    # live catalog: this model's input_modalities include "image".
    openrouter_model_vision: str = os.getenv(
        "OPENROUTER_MODEL_VISION", "google/gemma-4-31b-it:free"
    )

    # === Groq — free tier, fastest inference. https://console.groq.com/keys ===
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    groq_model_reasoning: str = os.getenv("GROQ_MODEL_REASONING", "moonshotai/kimi-k2-instruct")
    groq_model_analysis: str = os.getenv("GROQ_MODEL_ANALYSIS", "moonshotai/kimi-k2-instruct")
    groq_model_general: str = os.getenv("GROQ_MODEL_GENERAL", "llama-3.3-70b-versatile")
    groq_model_vision: str = os.getenv(
        "GROQ_MODEL_VISION", "meta-llama/llama-4-scout-17b-16e-instruct"
    )

    # === HuggingFace Inference Providers — paid fallback ===
    hf_api_key: str = os.getenv("HF_TOKEN", "") or os.getenv("HUGGINGFACE_API_KEY", "")
    hf_base_url: str = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1")
    hf_model_reasoning: str = os.getenv("HF_MODEL_REASONING", "MiniMaxAI/MiniMax-M2.7")
    hf_model_analysis: str = os.getenv("HF_MODEL_ANALYSIS", "MiniMaxAI/MiniMax-M2.7")
    hf_model_general: str = os.getenv("HF_MODEL_GENERAL", "meta-llama/Llama-3.3-70B-Instruct")
    # Llama 3.3 70B is text-only, so vision needs its own model here.
    hf_model_vision: str = os.getenv("HF_MODEL_VISION", "google/gemma-4-31B-it")

    # Output budget per agent. The agent prompts demand very long structured
    # reports; at 8000 the analysis agents were cut off mid-table
    # (finish_reason="length"). 16000 leaves headroom to finish cleanly.
    max_tokens: int = int(os.getenv("MAX_TOKENS", os.getenv("HF_MAX_TOKENS", "16000")))
    # Bound simultaneous agent calls to avoid bursting free-provider rate limits.
    pipeline_concurrency: int = max(1, int(os.getenv("PIPELINE_CONCURRENCY", "3")))

    # Sent by OpenRouter convention so the app is identifiable on their dashboard.
    app_url: str = os.getenv("APP_URL", "http://localhost:5173")
    app_name: str = "Unique Type Team"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    _MODELS = {
        "ik_llama": ("ik_llama_model", "ik_llama_model", "ik_llama_model", "ollama_vision_model"),
        "ollama": ("ollama_model", "ollama_model", "ollama_model", "ollama_vision_model"),
        "openrouter": ("openrouter_model_reasoning", "openrouter_model_analysis",
                       "openrouter_model_general", "openrouter_model_vision"),
        "groq": ("groq_model_reasoning", "groq_model_analysis",
                 "groq_model_general", "groq_model_vision"),
        "huggingface": ("hf_model_reasoning", "hf_model_analysis",
                        "hf_model_general", "hf_model_vision"),
    }
    _CREDS = {
        "ik_llama": ("ollama_api_key", "ik_llama_base_url"),
        "ollama": ("ollama_api_key", "ollama_base_url"),
        "openrouter": ("openrouter_api_key", "openrouter_base_url"),
        "groq": ("groq_api_key", "groq_base_url"),
        "huggingface": ("hf_api_key", "hf_base_url"),
    }

    # The SDK requires a nonempty key; local Ollama does not authenticate it.
    ollama_api_key: str = "ollama-local"
    ik_llama_base_url: str = os.getenv("IK_LLAMA_BASE_URL", "http://127.0.0.1:8081/v1")
    ik_llama_model: str = os.getenv("IK_LLAMA_MODEL", "qwen-local")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    ollama_vision_model: str = os.getenv("OLLAMA_VISION_MODEL", "")

    def models_for(self, provider: str) -> dict[str, str]:
        try:
            r, a, g, v = self._MODELS[provider]
        except KeyError:
            raise ValueError(f"Unknown provider: {provider}") from None
        return {
            "reasoning": getattr(self, r),
            "analysis": getattr(self, a),
            "general": getattr(self, g),
            "vision": getattr(self, v),
        }

    def credentials_for(self, provider: str) -> tuple[str, str]:
        try:
            k, u = self._CREDS[provider]
        except KeyError:
            raise ValueError(f"Unknown provider: {provider}") from None
        return getattr(self, k), getattr(self, u)

    def configured_providers(self) -> list[str]:
        return [
            p for p in self.provider_order
            if p in self._CREDS and self.credentials_for(p)[0]
        ]


settings = Settings()
