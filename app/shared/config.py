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
    # Fixed SMS code is local-dev only. staging/production ignore this flag (see auth service).
    sms_allow_dev_code: bool = True
    sms_dev_phone_whitelist: str = ""  # comma-separated; always allow fixed code
    sms_code_ttl_seconds: int = 300
    sms_send_interval_seconds: int = 60
    sms_daily_limit: int = 20
    sms_sign_name: str = ""
    sms_template_code: str = ""
    sms_access_key_id: str = ""
    sms_access_key_secret: str = ""

    # Content safety (text): local word list by default; aliyun|tencent are stubs until credentials exist
    content_safety_provider: str = "local"

    # Push (app notifications): log = write in-app notification only, no vendor push.
    # fcm | hms | mipush | oppo | vivo | apns → vendor adapters are placeholders (see ops/push_provider.py).
    push_provider: str = "log"
    push_fcm_credentials_json: str = ""  # path or inline service-account JSON
    push_apns_key_id: str = ""
    push_apns_team_id: str = ""
    push_apns_key_path: str = ""
    push_vendor_app_id: str = ""
    push_vendor_app_secret: str = ""

    # Identity (real-name / face): manual = admin review queue (current behaviour).
    # aliyun | tencent | wechat → placeholder adapters in trust/identity_provider.py.
    identity_provider: str = "manual"
    identity_access_key_id: str = ""
    identity_access_key_secret: str = ""

    # Map / geocoding: none = city text only, no coordinate lookups.
    # amap | tencent | baidu → placeholder adapters in shared/geo_provider.py.
    map_provider: str = "none"
    map_server_key: str = ""

    # CDN in front of media (empty = serve media_public_base / oss_public_endpoint directly)
    cdn_base_url: str = ""

    # Operational launch metadata (surfaced in admin → system status; not enforced)
    icp_record_no: str = ""  # e.g. 京ICP备XXXXXXXX号-X
    public_base_url: str = ""  # https://api.example.com
    privacy_policy_url: str = ""
    terms_url: str = ""

    # Analytics ingestion / retention / client config
    analytics_enabled: bool = True  # kill switch, also returned to clients
    analytics_sample_rate: float = 1.0  # global client-side sampling (per session)
    analytics_max_batch: int = 50
    analytics_max_event_age_days: int = 7  # older client events are rejected (clock/offline abuse)
    analytics_max_future_seconds: int = 300
    analytics_ingest_per_minute: int = 60  # per anon_id
    analytics_ingest_ip_per_minute: int = 240  # per IP (NAT friendly)
    analytics_retention_days: int = 180  # raw events; aggregates are kept
    analytics_ip_hash_days: int = 30  # ip_hash is nulled after this
    analytics_export_max_rows: int = 50_000
    analytics_query_max_days: int = 31

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

    # IM provider (noop stub; set IM_PROVIDER=tencent + TENCENT_IM_* for Tencent Cloud IM)
    im_provider: str = "noop"
    tencent_im_sdk_app_id: int = 0
    tencent_im_secret_key: str = ""
    tencent_im_admin_user: str = "administrator"
    tencent_im_usersig_expire_seconds: int = 604800  # 7 days

    # empty = json outside development, text in development
    log_format: str = ""
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
