from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    opencode_zen_api_key: str = ""
    gemini_api_key: str = ""
    nvidia_api_key: str = ""

    scorer_provider: Literal["opencode_zen", "gemini", "nvidia"] = "opencode_zen"
    scorer_fallback: Literal["opencode_zen", "gemini", "nvidia"] = "gemini"
    vision_extractor: Literal["opencode_zen", "gemini", "nvidia"] = "nvidia"
    nvidia_model: str = "nvidia/nemotron-3-super-120b"

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
