from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="LLM_",
    )

    API_KEY: str
    MODEL: str
    BASE_URL: str


class BrowserSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="BROWSER_",
    )

    HEADLESS: bool
    SLOW_MO: int
    VIEWPORT_WIDTH: int
    VIEWPORT_HEIGHT: int
    PAGE_TIMEOUT: int


llm_settings = LLMSettings()
browser_settings = BrowserSettings()
