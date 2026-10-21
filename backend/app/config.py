from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    # Application
    app_name: str = "Dockyard Materials Command"
    app_version: str = "1.0.0"
    debug: bool = True

    # Database. Required: the backend refuses to start without it rather than silently using a local
    # SQLite file. Any SQLAlchemy URL works, including sqlite:///... when chosen explicitly.
    database_url: str

    # CORS
    cors_origins: list[str] = [
        "http://localhost:8443",
        "http://localhost:5173",
        "http://127.0.0.1:8443",
        "http://127.0.0.1:5173",
    ]

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
