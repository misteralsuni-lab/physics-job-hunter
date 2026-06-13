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

    schedule_time: str = "08:00"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
