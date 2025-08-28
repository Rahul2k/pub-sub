# in-memory-pubsub-python-prod/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """
    # To generate a new secret key:
    # import secrets
    # secrets.token_hex(32)
    # This is not used in this simple app but is good practice for any real app.
    APP_NAME: str = "In-Memory Pub/Sub"
    LOG_LEVEL: str = "INFO"
    MAX_HISTORY_PER_TOPIC: int = 50

    # Pydantic V2 settings configuration
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

# Create a single settings instance to be used across the application
settings = Settings()