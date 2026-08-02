from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "plan-service"
    app_version: str = "1.0.0"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://teleportal:teleportal@localhost:5432/plans"
    )
    log_level: str = "INFO"

    model_config = {"env_prefix": "TELEPORTAL_"}


settings = Settings()
