from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """
    APP_NAME: str = "In-Memory Pub/Sub"
    LOG_LEVEL: str = "INFO"
    MAX_HISTORY_PER_TOPIC: int = 50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

# Create a single settings instance to be used across the application
settings = Settings()