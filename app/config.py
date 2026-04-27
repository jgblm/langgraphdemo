"""Configuration management."""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # LLM Settings
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # LangSmith Settings (Optional - for tracing)
    langsmith_api_key: Optional[str] = None
    langsmith_project: str = "langgraph-demo"
    langsmith_tracing_enabled: bool = True

    # Database Settings
    database_url: str = "postgresql+asyncpg://langgraph:langgraph123@localhost:5432/langgraphdb"
    sync_database_url: str = "postgresql://langgraph:langgraph123@localhost:5432/langgraphdb"

    # App Settings
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    @property
    def is_langsmith_configured(self) -> bool:
        """Check if LangSmith is properly configured."""
        return bool(self.langsmith_api_key)

    def setup_langsmith(self):
        """Setup LangSmith tracing if configured."""
        if self.langsmith_api_key:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key
            os.environ["LANGCHAIN_PROJECT"] = self.langsmith_project
            os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"


# Global settings instance
settings = Settings()
