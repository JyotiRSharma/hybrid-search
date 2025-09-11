from pydantic import BaseModel
import os

class Settings(BaseModel):
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@db:5432/postgres",
    )
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    KW_WEIGHT: float = float(os.getenv("KW_WEIGHT", 0.5))
    VEC_WEIGHT: float = float(os.getenv("VEC_WEIGHT", 0.5))

settings = Settings()
