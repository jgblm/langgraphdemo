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

    # Langfuse Settings (Optional - for tracing and monitoring)
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_project_id: Optional[str] = None
    langfuse_tracing_enabled: bool = True

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

    @property
    def is_langfuse_configured(self) -> bool:
        """Check if Langfuse is properly configured."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    def setup_langfuse(self):
        """Setup Langfuse tracing if configured."""
        if self.is_langfuse_configured:
            os.environ["LANGFUSE_PUBLIC_KEY"] = self.langfuse_public_key
            os.environ["LANGFUSE_SECRET_KEY"] = self.langfuse_secret_key
            os.environ["LANGFUSE_HOST"] = self.langfuse_host
            if self.langfuse_project_id:
                os.environ["LANGFUSE_PROJECT_ID"] = self.langfuse_project_id


# Global settings instance
settings = Settings()
