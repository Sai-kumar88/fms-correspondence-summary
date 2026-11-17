from typing import Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration loaded from environment variables and .env file.
    Follows 12-factor app principles with type safety via Pydantic.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application Information
    PROJECT_NAME: str = "FMS AI Correspondence Summary"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"

    # Server Configuration
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # File Validation Settings
    MAX_FILE_SIZE_MB: int = 25
    ALLOWED_EXTENSIONS: Set[str] = {
        ".pdf",
        ".docx",
        ".doc",
        ".txt",
    }

    # NVIDIA AI Model Configuration
    NVIDIA_API_KEY: str = ""
    NVIDIA_MODEL: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_TIMEOUT_SECONDS: float = 90.0
    NVIDIA_MAX_RETRIES: int = 3
    MAX_TEXT_CHARS: int = 30000  # Context window safety limit


settings = Settings()
