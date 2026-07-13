from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fec_api_key: str = "DEMO_KEY"
    fec_base_url: str = "https://api.open.fec.gov/v1"
    # Set false if local Python/SSL trust store fails (common on some Windows setups)
    fec_ssl_verify: bool = True

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
