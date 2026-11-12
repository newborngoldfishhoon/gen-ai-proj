"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/agentforge",
        alias="DATABASE_URL",
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        return v

    # Gemini AI
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.5-flash", alias="GEMINI_MODEL")

    # Groq AI
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-120b", alias="GROQ_MODEL")

    # App
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # LLM Provider: "groq", "gemini", or "mock"
    llm_provider: str = Field(default="groq", alias="LLM_PROVIDER")

    # Search & Tool Provider settings
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    search_provider: str = Field(default="tavily", alias="SEARCH_PROVIDER")
    agent_enable_web_search: bool = Field(default=True, alias="AGENT_ENABLE_WEB_SEARCH")
    agent_enable_calculator: bool = Field(default=True, alias="AGENT_ENABLE_CALCULATOR")

    # Agent and Tool limits
    max_tasks: int = Field(default=6, alias="MAX_TASKS")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    max_goal_length: int = Field(default=2000, alias="MAX_GOAL_LENGTH")
    max_search_results: int = Field(default=5, alias="MAX_SEARCH_RESULTS")
    max_tool_calls_per_task: int = Field(default=5, alias="MAX_TOOL_CALLS_PER_TASK")
    max_tool_calls_per_run: int = Field(default=15, alias="MAX_TOOL_CALLS_PER_RUN")
    tool_timeout_seconds: int = Field(default=30, alias="TOOL_TIMEOUT_SECONDS")
    max_extracted_chars: int = Field(default=8000, alias="MAX_EXTRACTED_CHARS")

    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
    )

    model_config = {
        "env_file": [".env", "../.env", "backend/.env"],
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }


# Singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return cached settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
