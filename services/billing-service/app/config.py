from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "billing-service"
    app_version: str = "1.0.0"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://teleportal:teleportal@localhost:5432/billing"
    )
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    subscriber_service_url: str = "http://subscriber-service:8000"
    plan_service_url: str = "http://plan-service:8000"
    usage_service_url: str = "http://usage-service:8000"
    log_level: str = "INFO"
    tax_rate: float = 0.21  # Belgian VAT

    model_config = {"env_prefix": "TELEPORTAL_"}


settings = Settings()
