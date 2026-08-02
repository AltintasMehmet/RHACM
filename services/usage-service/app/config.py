from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "usage-service"
    app_version: str = "1.0.0"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://teleportal:teleportal@localhost:5432/usage"
    )
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    log_level: str = "INFO"

    model_config = {"env_prefix": "TELEPORTAL_"}


settings = Settings()
