from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "subscriber-service"
    app_version: str = "1.0.0"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://teleportal:teleportal@localhost:5432/subscribers"
    )
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    plan_service_url: str = "http://plan-service:8000"
    log_level: str = "INFO"

    model_config = {"env_prefix": "TELEPORTAL_"}


settings = Settings()
