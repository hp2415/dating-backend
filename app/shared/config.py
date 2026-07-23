from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "dating-backend"

    database_url: str = "postgresql+asyncpg://dating:dating_dev_password@localhost:5432/dating"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production-use-long-random-string"
    jwt_access_ttl_minutes: int = 120
    jwt_refresh_ttl_days: int = 30

    oss_endpoint: str = "http://localhost:9000"
    oss_public_endpoint: str = "http://localhost:9000"
    oss_access_key: str = "minioadmin"
    oss_secret_key: str = "minioadmin"
    oss_bucket: str = "dating-media"
    oss_region: str = "us-east-1"

    # Development SMS: fixed code accepted; real SMS provider later
    sms_dev_code: str = "123456"
    sms_code_ttl_seconds: int = 300
    sms_send_interval_seconds: int = 60
    sms_daily_limit: int = 20

    # Age gate
    min_age: int = 18

    # Admin auth (independent from C-end SMS login)
    admin_jwt_secret: str = "change-me-admin-jwt-secret"
    admin_jwt_ttl_minutes: int = 480
    admin_default_username: str = "admin"
    admin_default_password: str = "Admin@123456"
    admin_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Discover / swipe
    discover_page_size: int = 10
    discover_exposure_ttl_seconds: int = 86400 * 3
    daily_like_limit: int = 100
    new_user_like_limit: int = 30
    seed_demo_users: bool = True
    seed_demo_user_count: int = 40

    # IM provider placeholder (M3: rongcloud / netease / easemob)
    im_provider: str = "noop"


settings = Settings()