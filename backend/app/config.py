from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "nvidia/nemotron-3-super-120b-a12b"
    database_url: str = "sqlite+aiosqlite:///./career.db"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    max_results: int = 200
    results_per_region: int = 12
    search_concurrency: int = 4
    search_scope_limit: int = 8
    max_job_age_days: int = 7
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.allowed_origins.split(",") if x.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
