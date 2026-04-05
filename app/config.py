from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://ariuslee@localhost:5432/orionmano"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "orionmano-dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24

    ANTHROPIC_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    CORS_ORIGINS: str = '["http://localhost:3020"]'
    UPLOAD_DIR: str = "./uploads"

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
