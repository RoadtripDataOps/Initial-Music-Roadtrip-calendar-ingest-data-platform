from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_ADMIN_PASSWORD_HASH = (
    "pbkdf2_sha256$600000$ApKBAhoPrfu0FDx0dR8Phg$"
    "wRZuGUp-fp2WAIYU5z5N48YV-ctUCRhEqk81Gzxkxas"
)
DEV_SESSION_SECRET_KEY = "development-only-calendar-ingest-session-secret"


class Settings(BaseSettings):
    """Runtime settings for the local POC."""

    app_name: str = "Music Roadtrip Calendar Ingest"
    database_url: str = Field(
        default="sqlite:///./calendar_ingest.db",
        validation_alias=AliasChoices(
            "DATABASE_URL",
            "CALENDAR_INGEST_DATABASE_URL",
        ),
    )
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices(
            "APP_ENV",
            "CALENDAR_INGEST_ENVIRONMENT",
        ),
    )
    risk_hash_salt: str = "local-calendar-ingest-poc"
    minimum_form_seconds: int = 2
    turnstile_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "TURNSTILE_ENABLED",
            "CALENDAR_INGEST_TURNSTILE_ENABLED",
        ),
    )
    turnstile_site_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TURNSTILE_SITE_KEY",
            "CALENDAR_INGEST_TURNSTILE_SITE_KEY",
        ),
    )
    turnstile_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TURNSTILE_SECRET_KEY",
            "CALENDAR_INGEST_TURNSTILE_SECRET_KEY",
        ),
    )
    turnstile_verify_url: str = Field(
        default="https://challenges.cloudflare.com/turnstile/v0/siteverify",
        validation_alias=AliasChoices(
            "TURNSTILE_VERIFY_URL",
            "CALENDAR_INGEST_TURNSTILE_VERIFY_URL",
        ),
    )
    public_submit_rate_limit_per_ip_per_hour: int = Field(
        default=8,
        validation_alias=AliasChoices(
            "PUBLIC_SUBMIT_RATE_LIMIT_PER_IP_PER_HOUR",
            "CALENDAR_INGEST_PUBLIC_SUBMIT_RATE_LIMIT_PER_IP_PER_HOUR",
        ),
    )
    public_submit_rate_limit_per_email_per_day: int = Field(
        default=20,
        validation_alias=AliasChoices(
            "PUBLIC_SUBMIT_RATE_LIMIT_PER_EMAIL_PER_DAY",
            "CALENDAR_INGEST_PUBLIC_SUBMIT_RATE_LIMIT_PER_EMAIL_PER_DAY",
        ),
    )
    public_submit_rate_limit_per_domain_per_day: int = Field(
        default=40,
        validation_alias=AliasChoices(
            "PUBLIC_SUBMIT_RATE_LIMIT_PER_DOMAIN_PER_DAY",
            "CALENDAR_INGEST_PUBLIC_SUBMIT_RATE_LIMIT_PER_DOMAIN_PER_DAY",
        ),
    )
    public_submit_rate_limit_per_route_per_hour: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "PUBLIC_SUBMIT_RATE_LIMIT_PER_ROUTE_PER_HOUR",
            "CALENDAR_INGEST_PUBLIC_SUBMIT_RATE_LIMIT_PER_ROUTE_PER_HOUR",
        ),
    )
    public_submit_global_rate_limit_per_hour: int = Field(
        default=100,
        validation_alias=AliasChoices(
            "PUBLIC_SUBMIT_GLOBAL_RATE_LIMIT_PER_HOUR",
            "CALENDAR_INGEST_PUBLIC_SUBMIT_GLOBAL_RATE_LIMIT_PER_HOUR",
        ),
    )
    public_file_upload_max_size_mb: int = Field(
        default=5,
        validation_alias=AliasChoices(
            "PUBLIC_FILE_UPLOAD_MAX_SIZE_MB",
            "CALENDAR_INGEST_PUBLIC_FILE_UPLOAD_MAX_SIZE_MB",
        ),
    )
    public_file_upload_max_rows: int = Field(
        default=1000,
        validation_alias=AliasChoices(
            "PUBLIC_FILE_UPLOAD_MAX_ROWS",
            "CALENDAR_INGEST_PUBLIC_FILE_UPLOAD_MAX_ROWS",
        ),
    )
    crawler_max_redirects: int = 5
    crawler_timeout_seconds: float = 10.0
    crawler_max_response_bytes: int = 2_000_000
    crawler_dns_resolution_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CRAWLER_DNS_RESOLUTION_ENABLED",
            "CALENDAR_INGEST_CRAWLER_DNS_RESOLUTION_ENABLED",
        ),
    )
    admin_username: str = Field(
        default="admin",
        validation_alias=AliasChoices(
            "ADMIN_USERNAME",
            "CALENDAR_INGEST_ADMIN_USERNAME",
        ),
    )
    admin_password_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ADMIN_PASSWORD_HASH",
            "CALENDAR_INGEST_ADMIN_PASSWORD_HASH",
        ),
    )
    session_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SESSION_SECRET_KEY",
            "CALENDAR_INGEST_SESSION_SECRET_KEY",
        ),
    )
    admin_session_timeout_minutes: int = Field(
        default=480,
        validation_alias=AliasChoices(
            "ADMIN_SESSION_TIMEOUT_MINUTES",
            "CALENDAR_INGEST_ADMIN_SESSION_TIMEOUT_MINUTES",
        ),
    )
    admin_cookie_samesite: str = Field(
        default="lax",
        validation_alias=AliasChoices(
            "ADMIN_COOKIE_SAMESITE",
            "CALENDAR_INGEST_ADMIN_COOKIE_SAMESITE",
        ),
    )
    admin_login_rate_limit_per_ip_per_hour: int = Field(
        default=8,
        validation_alias=AliasChoices(
            "ADMIN_LOGIN_RATE_LIMIT_PER_IP_PER_HOUR",
            "CALENDAR_INGEST_ADMIN_LOGIN_RATE_LIMIT_PER_IP_PER_HOUR",
        ),
    )
    admin_require_sso_gate: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ADMIN_REQUIRE_SSO_GATE",
            "CALENDAR_INGEST_ADMIN_REQUIRE_SSO_GATE",
        ),
    )
    cityspark_provider_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "CITY" + "SPARK_PROVIDER_ENABLED",
            "CALENDAR_INGEST_CITY" + "SPARK_PROVIDER_ENABLED",
        ),
    )
    cityspark_live_calls_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CITY" + "SPARK_LIVE_CALLS_ENABLED",
            "CALENDAR_INGEST_CITY" + "SPARK_LIVE_CALLS_ENABLED",
        ),
    )
    cityspark_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CITY" + "SPARK_API_KEY",
            "CALENDAR_INGEST_CITY" + "SPARK_API_KEY",
        ),
    )
    cityspark_portal_script_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CITY" + "SPARK_PORTAL_SCRIPT_ID",
            "CALENDAR_INGEST_CITY" + "SPARK_PORTAL_SCRIPT_ID",
        ),
    )
    cityspark_base_url: str = Field(
        default="https://api." + ("city" + "spark") + ".com",
        validation_alias=AliasChoices(
            "CITY" + "SPARK_BASE_URL",
            "CALENDAR_INGEST_CITY" + "SPARK_BASE_URL",
        ),
    )
    cityspark_default_page_size: int = Field(
        default=200,
        validation_alias=AliasChoices(
            "CITY" + "SPARK_DEFAULT_PAGE_SIZE",
            "CALENDAR_INGEST_CITY" + "SPARK_DEFAULT_PAGE_SIZE",
        ),
    )
    cityspark_sandbox_max_events: int = Field(
        default=1000,
        validation_alias=AliasChoices(
            "CITY" + "SPARK_SANDBOX_MAX_EVENTS",
            "CALENDAR_INGEST_CITY" + "SPARK_SANDBOX_MAX_EVENTS",
        ),
    )
    jambase_live_calls_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "JAMBASE_LIVE_CALLS_ENABLED",
            "CALENDAR_INGEST_JAMBASE_LIVE_CALLS_ENABLED",
        ),
    )
    jambase_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "JAMBASE_API_KEY",
            "CALENDAR_INGEST_JAMBASE_API_KEY",
        ),
    )
    jambase_base_url: str = Field(
        default="https://api.data.jambase.com/v3",
        validation_alias=AliasChoices(
            "JAMBASE_BASE_URL",
            "CALENDAR_INGEST_JAMBASE_BASE_URL",
        ),
    )
    jambase_default_per_page: int = Field(
        default=100,
        validation_alias=AliasChoices(
            "JAMBASE_DEFAULT_PER_PAGE",
            "CALENDAR_INGEST_JAMBASE_DEFAULT_PER_PAGE",
        ),
    )
    jambase_sandbox_max_events: int = Field(
        default=1000,
        validation_alias=AliasChoices(
            "JAMBASE_SANDBOX_MAX_EVENTS",
            "CALENDAR_INGEST_JAMBASE_SANDBOX_MAX_EVENTS",
        ),
    )
    app_feed_public: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "APP_FEED_PUBLIC",
            "CALENDAR_INGEST_APP_FEED_PUBLIC",
        ),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CALENDAR_INGEST_",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def effective_admin_password_hash(self) -> str:
        if self.admin_password_hash:
            return self.admin_password_hash
        if self.is_production:
            raise RuntimeError("ADMIN_PASSWORD_HASH is required in production.")
        return DEV_ADMIN_PASSWORD_HASH

    @property
    def effective_session_secret_key(self) -> str:
        if self.session_secret_key:
            return self.session_secret_key
        if self.is_production:
            raise RuntimeError("SESSION_SECRET_KEY is required in production.")
        return DEV_SESSION_SECRET_KEY


@lru_cache
def get_settings() -> Settings:
    """Return cached app settings loaded from environment variables."""

    return Settings()
