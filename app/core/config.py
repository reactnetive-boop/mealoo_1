# ---------------------------------------------------------
# APPLICATION CONFIGURATION
# Loads all environment variables
# ---------------------------------------------------------

from dotenv import load_dotenv
import logging
import os

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


APP_NAME = os.getenv("APP_NAME", "Orleeno")

# development | staging | production. Anything that weakens security
# (OTP echo, API docs, ...) is refused when this is "production".
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = os.getenv("DATABASE_URL") or (
    f"postgresql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
# Railway / Heroku style URLs use the legacy scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# Connection pool. The API serves sync endpoints from a ~40 thread pool and
# the scheduler needs its own connections, so the SQLAlchemy defaults (5 + 10)
# are too small. Keep pool_size + max_overflow (x replicas) under the
# database's max_connections.
DB_POOL_SIZE = _int("DB_POOL_SIZE", 10)
DB_MAX_OVERFLOW = _int("DB_MAX_OVERFLOW", 20)
DB_POOL_TIMEOUT_SECONDS = _int("DB_POOL_TIMEOUT_SECONDS", 30)
DB_POOL_RECYCLE_SECONDS = _int("DB_POOL_RECYCLE_SECONDS", 1800)
# Any single SQL statement running longer than this is cancelled (0 = off)
DB_STATEMENT_TIMEOUT_MS = _int("DB_STATEMENT_TIMEOUT_MS", 30000)

# Shared store for rate limits and login back-off across replicas (optional;
# without it each process counts on its own).
REDIS_URL = os.getenv("REDIS_URL") or None

# ── Observability ────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
# "json" (one JSON object per line, default in production) or "text"
LOG_FORMAT = (os.getenv("LOG_FORMAT") or ("json" if IS_PRODUCTION else "text")).strip().lower()
# Error reporting is enabled only when a DSN is configured
SENTRY_DSN = os.getenv("SENTRY_DSN") or None
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE") or 0)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Key for encrypting bank account numbers (a Fernet key: generate with
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").
# Earlier keys stay readable when listed in DATA_ENCRYPTION_OLD_KEYS.
DATA_ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY") or None
DATA_ENCRYPTION_OLD_KEYS = [k for k in (os.getenv("DATA_ENCRYPTION_OLD_KEYS") or "").split(",") if k.strip()]

# Mobile apps (customer / kitchen / delivery) and the admin panel get
# separate lifetimes: admin sessions are short because they can move money.
ACCESS_TOKEN_EXPIRE_MINUTES = _int("ACCESS_TOKEN_EXPIRE_MINUTES", 10080)
ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES = _int("ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES", 720)
# When true, admins without two-factor login are sent to enrol right after login
ADMIN_2FA_REQUIRED = _bool("ADMIN_2FA_REQUIRED", False)

# All business dates (meal dates, cut-offs, midnight jobs) are in this zone.
BUSINESS_TIMEZONE = os.getenv("BUSINESS_TIMEZONE", "Asia/Kolkata")

# ── OTP ──────────────────────────────────────────────────
OTP_TTL_MINUTES = _int("OTP_TTL_MINUTES", 10)
OTP_MAX_ATTEMPTS = _int("OTP_MAX_ATTEMPTS", 5)
OTP_RESEND_COOLDOWN_SECONDS = _int("OTP_RESEND_COOLDOWN_SECONDS", 30)
OTP_MAX_PER_HOUR = _int("OTP_MAX_PER_HOUR", 5)
PASSWORD_RESET_TOKEN_TTL_MINUTES = _int("PASSWORD_RESET_TOKEN_TTL_MINUTES", 10)

# Development convenience: outside production the OTP is also echoed in the API
# response (no phone needed). Production never does this; OTPs go by SMS (SMS_PROVIDER).
OTP_ECHO_IN_RESPONSE = _bool("OTP_ECHO_IN_RESPONSE", not IS_PRODUCTION) and not IS_PRODUCTION

# Push notifications: "expo" (Expo push service) or "none"
PUSH_PROVIDER = (os.getenv("PUSH_PROVIDER") or ("none" if APP_ENV == "test" else "expo")).strip().lower()
EXPO_ACCESS_TOKEN = os.getenv("EXPO_ACCESS_TOKEN") or None

# SMS gateway for OTPs: console (development), msg91, twilio or none
SMS_PROVIDER = (os.getenv("SMS_PROVIDER") or ("none" if IS_PRODUCTION else "console")).strip().lower()
MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY") or None
MSG91_TEMPLATE_ID = os.getenv("MSG91_TEMPLATE_ID") or None
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID") or None
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN") or None
TWILIO_FROM = os.getenv("TWILIO_FROM") or None

# ── Login brute-force protection ─────────────────────────
# Wrong passwords are counted per (account, client IP): after
# LOGIN_MAX_FAILED_ATTEMPTS that IP waits LOGIN_LOCKOUT_MINUTES, doubling with
# every further failure up to LOGIN_LOCKOUT_MAX_MINUTES. Someone who only knows
# a phone number therefore locks out themselves, not the owner.
LOGIN_MAX_FAILED_ATTEMPTS = _int("LOGIN_MAX_FAILED_ATTEMPTS", 5)
LOGIN_LOCKOUT_MINUTES = _int("LOGIN_LOCKOUT_MINUTES", 15)
LOGIN_LOCKOUT_MAX_MINUTES = _int("LOGIN_LOCKOUT_MAX_MINUTES", 24 * 60)
LOGIN_FAILURE_WINDOW_MINUTES = _int("LOGIN_FAILURE_WINDOW_MINUTES", 24 * 60)
# Account-wide lock (stored on the account row) only for a distributed attack
# from many IPs.
LOGIN_ACCOUNT_LOCK_THRESHOLD = _int("LOGIN_ACCOUNT_LOCK_THRESHOLD", 50)

# ── Delivery / pickup codes ──────────────────────────────
DELIVERY_CODE_MAX_ATTEMPTS = _int("DELIVERY_CODE_MAX_ATTEMPTS", 5)
# Wrong kitchen pickup codes allowed per order before it locks for admin help
PICKUP_CODE_MAX_ATTEMPTS = _int("PICKUP_CODE_MAX_ATTEMPTS", 5)
# Wrong pickup codes one partner may enter per business day across all orders
PICKUP_CODE_DAILY_FAILURE_LIMIT = _int("PICKUP_CODE_DAILY_FAILURE_LIMIT", 10)
# A customer delivery code stays valid this long after the delivery day ends
# (late dinners handed over just after midnight)
DELIVERY_CODE_GRACE_HOURS = _int("DELIVERY_CODE_GRACE_HOURS", 3)
# A partner can report "could not deliver" this long after tapping "arrived"
DELIVERY_FAILED_WAIT_MINUTES = _int("DELIVERY_FAILED_WAIT_MINUTES", 10)
# Key for deriving pickup / delivery codes. Falls back to a key derived from
# JWT_SECRET_KEY; set it separately to rotate codes without logging everyone out.
VERIFICATION_CODE_SECRET = os.getenv("VERIFICATION_CODE_SECRET") or None

# Legacy flat payout per delivery. Only used to seed the pricing table and for
# orders created before pricing snapshots existed.
DELIVERY_BOY_FEE_PER_DELIVERY = os.getenv(
    "DELIVERY_BOY_FEE_PER_DELIVERY",
    "30.00"
)

# ── Internal wallet top-up (no payment gateway in this phase) ─
WALLET_TOPUP_MAX_AMOUNT = os.getenv("WALLET_TOPUP_MAX_AMOUNT", "10000.00")
WALLET_TOPUP_DAILY_LIMIT = os.getenv("WALLET_TOPUP_DAILY_LIMIT", "25000.00")
# Self top-up adds wallet money WITHOUT any real payment (there is no gateway
# yet). It exists for development / staging testing only, so production
# keeps it off unless explicitly enabled; there, wallet money is added by an
# admin credit that records where the money came from.
WALLET_SELF_TOPUP_ENABLED = _bool("WALLET_SELF_TOPUP_ENABLED", not IS_PRODUCTION)

# Payment gateway for wallet top-ups: "none" (internal top-up only) or "razorpay"
PAYMENT_GATEWAY = (os.getenv("PAYMENT_GATEWAY") or "none").strip().lower()
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID") or None
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET") or None
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET") or None

# ── Ordering windows ─────────────────────────────────────
EXTRA_ORDER_MAX_DAYS_AHEAD = _int("EXTRA_ORDER_MAX_DAYS_AHEAD", 9)
SUBSCRIPTION_MAX_START_DAYS_AHEAD = _int("SUBSCRIPTION_MAX_START_DAYS_AHEAD", 30)
CUSTOM_PLAN_MIN_DAYS = _int("CUSTOM_PLAN_MIN_DAYS", 1)
CUSTOM_PLAN_MAX_DAYS = _int("CUSTOM_PLAN_MAX_DAYS", 90)

# ── Uploads ──────────────────────────────────────────────
# Must be a persistent volume in production, otherwise images vanish on deploy.
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_UPLOAD_BYTES = _int("MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
# Photos are re-encoded (metadata such as GPS stripped) and scaled down to this
MAX_IMAGE_DIMENSION = _int("MAX_IMAGE_DIMENSION", 1600)
# "local" (UPLOAD_DIR) or "s3" (any S3-compatible bucket: AWS S3, Cloudflare R2, MinIO)
STORAGE_BACKEND = (os.getenv("STORAGE_BACKEND") or "local").strip().lower()
S3_BUCKET = os.getenv("S3_BUCKET") or None
S3_REGION = os.getenv("S3_REGION") or None
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") or None
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID") or None
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY") or None
# CDN / public bucket URL for menu and profile photos; without it, signed URLs are used
S3_PUBLIC_BASE_URL = os.getenv("S3_PUBLIC_BASE_URL") or None
MAX_REQUEST_BYTES = _int("MAX_REQUEST_BYTES", 8 * 1024 * 1024)

# ── HTTP ─────────────────────────────────────────────────
# Comma separated list of browser origins allowed to call the API (admin panel etc).
# Example: CORS_ORIGINS=http://localhost:5173,https://admin.mealoo.in
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip() and o.strip() != "*"
]

ENABLE_API_DOCS = _bool("ENABLE_API_DOCS", not IS_PRODUCTION)

# Only one process may run the scheduler; API replicas set this to false.
RUN_SCHEDULER = _bool("RUN_SCHEDULER", True)
# Past-day orders still open are cancelled + refunded only this far back
STALE_SWEEP_LOOKBACK_DAYS = _int("STALE_SWEEP_LOOKBACK_DAYS", 7)

# ── Retention and checks (nightly maintenance job) ───────
OTP_LOG_RETENTION_DAYS = _int("OTP_LOG_RETENTION_DAYS", 30)
# Only notifications the user has read are purged
NOTIFICATION_RETENTION_DAYS = _int("NOTIFICATION_RETENTION_DAYS", 90)
# 0 = keep audit logs forever. Ledgers, orders and payments are never purged.
AUDIT_LOG_RETENTION_MONTHS = _int("AUDIT_LOG_RETENTION_MONTHS", 0)
# A withdrawal waiting longer than this is reported by reconciliation
PAYOUT_PENDING_ALERT_DAYS = _int("PAYOUT_PENDING_ALERT_DAYS", 3)
# An open complaint older than this is shown as overdue to admins
COMPLAINT_SLA_HOURS = _int("COMPLAINT_SLA_HOURS", 24)

# Comma separated proxies whose X-Forwarded-For is trusted for rate limiting.
TRUST_PROXY_HEADERS = _bool("TRUST_PROXY_HEADERS", False)


def validate_settings() -> None:
    """Refuse to boot with settings that would make the deployment insecure."""

    problems = []

    if not JWT_SECRET_KEY:
        problems.append("JWT_SECRET_KEY is not set")
    elif IS_PRODUCTION and len(JWT_SECRET_KEY) < 32:
        problems.append("JWT_SECRET_KEY must be at least 32 characters in production")

    if JWT_ALGORITHM not in ("HS256", "HS384", "HS512"):
        problems.append("JWT_ALGORITHM must be an HMAC algorithm (HS256/HS384/HS512)")

    if IS_PRODUCTION and any(o.startswith("http://") and "localhost" not in o for o in CORS_ORIGINS):
        problems.append("CORS_ORIGINS must use https:// origins in production")

    if STORAGE_BACKEND not in ("local", "s3"):
        problems.append("STORAGE_BACKEND must be 'local' or 's3'")
    elif STORAGE_BACKEND == "s3" and not S3_BUCKET:
        problems.append("S3_BUCKET is required when STORAGE_BACKEND=s3")

    if SMS_PROVIDER not in ("console", "msg91", "twilio", "none"):
        problems.append("SMS_PROVIDER must be console, msg91, twilio or none")
    elif SMS_PROVIDER == "console" and IS_PRODUCTION:
        problems.append("SMS_PROVIDER=console only logs OTPs; use msg91 or twilio in production")
    elif SMS_PROVIDER == "msg91" and not (MSG91_AUTH_KEY and MSG91_TEMPLATE_ID):
        problems.append("SMS_PROVIDER=msg91 needs MSG91_AUTH_KEY and MSG91_TEMPLATE_ID")
    elif SMS_PROVIDER == "twilio" and not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM):
        problems.append("SMS_PROVIDER=twilio needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM")

    if PAYMENT_GATEWAY not in ("none", "razorpay"):
        problems.append("PAYMENT_GATEWAY must be none or razorpay")
    elif PAYMENT_GATEWAY == "razorpay" and not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET):
        problems.append("PAYMENT_GATEWAY=razorpay needs RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET")

    if LOG_FORMAT not in ("json", "text"):
        problems.append("LOG_FORMAT must be 'json' or 'text'")

    if IS_PRODUCTION and SMS_PROVIDER == "none":
        logging.getLogger("app.config").warning(
            "SMS_PROVIDER is not set: OTPs are not sent, so registration and password reset cannot complete"
        )

    if problems:
        raise RuntimeError("Invalid configuration: " + "; ".join(problems))
