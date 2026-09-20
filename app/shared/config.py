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

    # Media storage: local disk by default; set STORAGE_DRIVER=oss to use MinIO/Aliyun.
    # Contract (sts → PUT → complete) is unchanged when switching drivers.
    storage_driver: str = "local"  # local | oss
    media_local_root: str = "./data/media"
    media_public_base: str = ""  # e.g. http://123.56.118.242 ; empty → derive from request
    media_upload_token_ttl_seconds: int = 600
    media_max_upload_bytes: int = 20 * 1024 * 1024
    media_auto_approve: bool = True  # decoupled from APP_ENV

    # SMS: provider abstraction (log = no external send). Dev code decoupled from APP_ENV.
    sms_provider: str = "log"  # log | aliyun | tencent
    sms_dev_code: str = "123456"
    sms_allow_dev_code: bool = True  # local/staging; set false in production
    sms_dev_phone_whitelist: str = ""  # comma-separated; always allow fixed code
    sms_code_ttl_seconds: int = 300
    sms_send_interval_seconds: int = 60
    sms_daily_limit: int = 20
    sms_sign_name: str = ""
    sms_template_code: str = ""
    sms_access_key_id: str = ""
    sms_access_key_secret: str = ""

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

    # IM provider (noop stub; swap to rongcloud / netease / tencent without route changes)
    im_provider: str = "noop"

    # M3 foundation
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    rate_limit_per_minute: int = 300
    idempotency_ttl_seconds: int = 86400
    domain_event_batch_size: int = 50
    worker_queues: str = "default,notify,moderation,stats"

    # M4 commerce (stub payments by default — real channels later)
    payment_provider: str = "stub"
    payment_stub_auto_complete: bool = True
    payment_refund_to_wallet: bool = True
    order_expire_minutes: int = 15
    wallet_welcome_cents: int = 50_000


settings = Settings()
