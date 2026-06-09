from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # GitHub
    github_app_id: int = 0
    github_private_key_path: str = "./private-key.pem"
    github_webhook_secret: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Limits
    debug: bool = False
    max_files_per_pr: int = 20
    max_lines_per_file: int = 500
    context_lines: int = 5

    database_url: str = ""


settings = Settings()
