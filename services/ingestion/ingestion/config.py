from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    minio_endpoint: str = "http://localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    s3_bucket_bronze: str = "bronze"

    user_agent: str = "rag-lakehouse-crawler/0.1 (+https://github.com/akashjack/rag-lakehouse)"
    request_timeout_s: int = 30
    crawl_concurrency: int = 4
    max_pages_per_source: int = 50  # cap for dev — raise later

    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
