"""Application settings, loaded from environment variables."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database -------------------------------------------------------
    postgres_user: str = "jobfndr"
    postgres_password: str = "jobfndr"
    postgres_db: str = "jobfndr"
    postgres_host: str = "db"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # --- Embeddings -----------------------------------------------------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    # Writable cache path so the model is baked into the image layer / kept in
    # a volume rather than re-downloaded on every container start.
    hf_home: str = "/models"

    # --- Ranking weights (configurable) ---------------------------------
    rule_weight: float = 0.4
    semantic_weight: float = 0.6

    # --- LLM (proposal drafting) ----------------------------------------
    # Leave llm_api_key empty until you have a key; the proposal service then
    # falls back to a deterministic local template draft.
    llm_provider: Literal["anthropic", "openai", "none"] = "anthropic"
    llm_api_key: str = ""
    llm_model: str = "claude-opus-5"
    llm_max_tokens: int = 1200
    llm_timeout_seconds: float = 60.0

    # --- Fetching -------------------------------------------------------
    http_timeout_seconds: float = 20.0
    # A contact address in the User-Agent is polite-crawling etiquette: it
    # gives an operator someone to reach if a fetch causes trouble.
    http_user_agent_template: str = (
        "JobFndr/1.0 (personal single-user job search agent{contact})"
    )

    @property
    def http_user_agent(self) -> str:
        contact = f"; contact: {self.operator_email}" if self.operator_email else ""
        return self.http_user_agent_template.format(contact=contact)
    respect_robots: bool = True
    max_jobs_per_source: int = 200

    # --- Operator (the single user) --------------------------------------
    # Seeds the one user_profile row and identifies the crawler. Override in
    # .env; a CV upload replaces the name/email with whatever it parses.
    operator_name: str = "Me"
    operator_email: str = ""
    operator_location: str = ""

    # --- App ------------------------------------------------------------
    cv_storage_dir: str = "/data/cv"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
