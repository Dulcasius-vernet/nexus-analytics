from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql://nexus_app:local_dev_change_me@localhost:5432/nexus_analytics"
    snwolley_api_key: str = ""
    snwolley_api_url: str = "https://v1.snwolley.ai/v1/chat/completions/assignment"
    session_secret: str = "local-only-change-this-session-secret-before-deployment"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
