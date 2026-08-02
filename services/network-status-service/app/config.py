from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "network-status-service"
    app_version: str = "1.0.0"
    debug: bool = False
    redis_url: str = "redis://localhost:6379/1"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    log_level: str = "INFO"

    model_config = {"env_prefix": "TELEPORTAL_"}


settings = Settings()
