from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://cadorim:cadorim@localhost:5432/cadorim_engine"
    wallet_api_base: str = "https://api.cadorim.com"
    wallet_api_key: str = ""
    sync_interval_minutes: int = 5

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
