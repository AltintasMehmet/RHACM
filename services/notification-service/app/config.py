from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "notification-service"
    app_version: str = "1.0.0"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://teleportal:teleportal@localhost:5432/notifications"
    )
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    log_level: str = "INFO"

    model_config = {"env_prefix": "TELEPORTAL_"}


settings = Settings()
