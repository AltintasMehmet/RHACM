from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "api-gateway"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    subscriber_service_url: str = "http://subscriber-service:8000"
    plan_service_url: str = "http://plan-service:8000"
    usage_service_url: str = "http://usage-service:8000"
    billing_service_url: str = "http://billing-service:8000"
    notification_service_url: str = "http://notification-service:8000"
    network_service_url: str = "http://network-status-service:8000"

    request_timeout: float = 30.0

    model_config = {"env_prefix": "TELEPORTAL_"}


settings = Settings()
