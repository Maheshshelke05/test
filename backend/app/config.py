from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-change-me"
DEV_WEBHOOK_SECRET = "dev-webhook-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"  # local | test | production
    database_url: str = "sqlite:///./campusbite.db"
    redis_url: str | None = None

    jwt_secret: str = DEV_JWT_SECRET
    access_token_minutes: int = 60 * 12
    refresh_token_days: int = 30

    # Local mode uses a deterministic OTP (123456, shown in the app) so no SMS provider is needed.
    otp_test_code: str = "123456"
    # Production pilot without an SMS provider: every OTP is this secret code, never shown in
    # the app. Leave empty once a real SMS provider is wired in (codes are then random).
    otp_fixed_code: str | None = None
    otp_ttl_seconds: int = 300
    otp_max_requests_per_10min: int = 5
    otp_max_verify_attempts: int = 5

    pickup_code_ttl_minutes: int = 30
    pickup_max_attempts: int = 5

    tax_bps: int = 500  # 5% GST on food, in basis points
    platform_fee_paise: int = 0
    commission_bps: int = 500  # platform commission used in reports

    unpaid_order_expiry_minutes: int = 15
    accept_timeout_minutes: int = 10

    webhook_secret: str = DEV_WEBHOOK_SECRET
    cors_origins: str = "*"
    worker_interval_seconds: int = 10
    run_worker: bool = True
    # Production runs migrations once before starting the API workers (systemd ExecStartPre),
    # so several workers don't race to migrate the same database.
    run_migrations: bool = True

    @property
    def is_local(self) -> bool:
        return self.env in ("local", "test")

    def check_production(self) -> None:
        """Refuse to start a non-local deployment with development secrets."""
        if self.is_local:
            return
        problems = []
        if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be a random string of at least 32 characters")
        if self.webhook_secret == DEV_WEBHOOK_SECRET:
            problems.append("WEBHOOK_SECRET must be changed")
        if self.otp_fixed_code is not None and not (self.otp_fixed_code.isdigit() and len(self.otp_fixed_code) == 6):
            problems.append("OTP_FIXED_CODE must be 6 digits")
        if self.otp_fixed_code == self.otp_test_code:
            problems.append("OTP_FIXED_CODE must not be the public test code")
        if problems:
            raise RuntimeError("Unsafe production settings: " + "; ".join(problems))


settings = Settings()
