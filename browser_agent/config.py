from pydantic_settings import BaseSettings, SettingsConfigDict

class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    OPENAI_API_KEY: str
    OPENAI_MODEL: str
    OPENAI_BASE_URL: str
