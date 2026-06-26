from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    opencode_zen_api_key: str = ""
    gemini_api_key: str = ""
    nvidia_api_key: str = ""
    openrouter_api_key: str = ""
    groq_api_key: str = ""

    scorer_provider: Literal["opencode_zen", "gemini", "nvidia", "openrouter"] = "opencode_zen"
    scorer_fallback: Literal["opencode_zen", "gemini", "nvidia", "openrouter"] = "gemini"
    vision_extractor: Literal["opencode_zen", "gemini", "nvidia", "openrouter"] = "nvidia"
    nvidia_model: str = "nvidia/nemotron-3-super-120b-a12b"
    nvidia_backup_model: str = "nvidia/nemotron-3-nano-30b-a3b"
    openrouter_model: str = "google/gemma-4-31b-it:free"
    groq_model: str = "qwen/qwen3-32b"

    supabase_url: str = ""
    supabase_service_role_key: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    email_provider: Literal["resend", "smtp", ""] = ""
    resend_api_key: str = ""
    email_from: str = ""
    email_to: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    firecrawl_api_key: str = ""

    # ---- Search Associates authenticated scraper ----------------------
    # Read from .env as SA_USERNAME / SA_PASSWORD.  When either is empty
    # the scraper logs once and returns [] — no login attempt is made.
    sa_username: str = ""
    sa_password: str = ""

    notify_score_threshold: int = 50
    research_score_threshold: int = 60
    schedule_time: str = "08:00"

    # ---- Dual-pathway: tutoring branch (v1) ------------------------------
    # See docs/dual-pathway.md §13 for sourcing of these defaults.
    tutoring_min_rate_usd: float = 32.0  # ~£25/hr; below = low_budget_hold
    tutoring_proposal_score_threshold: int = 60
    tutoring_parse_interval_min: int = 15
    tutoring_parse_timeout_s: int = 60
    tutoring_in_scope_curricula: str = (
        "IGCSE_Edexcel,IGCSE_CIE,A-Level_Edexcel,A-Level_CIE"
    )
    tutoring_out_of_scope_hold: bool = True
    tutoring_rate_band_default_usd: float = 45.0  # midpoint of 35-60 band

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
