from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "dashboard"
    app_version: str = "1.0.0"
    api_gateway_url: str = "http://api-gateway:8000"

    model_config = {"env_prefix": "TELEPORTAL_"}


settings = Settings()
