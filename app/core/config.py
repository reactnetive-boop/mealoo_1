# ---------------------------------------------------------
# APPLICATION CONFIGURATION
# Loads all environment variables
# ---------------------------------------------------------

from dotenv import load_dotenv
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

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Mobile apps (customer / kitchen / delivery) and the admin panel get
# separate lifetimes: admin sessions are short because they can move money.
ACCESS_TOKEN_EXPIRE_MINUTES = _int("ACCESS_TOKEN_EXPIRE_MINUTES", 10080)
ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES = _int("ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES", 720)

# All business dates (meal dates, cut-offs, midnight jobs) are in this zone.
BUSINESS_TIMEZONE = os.getenv("BUSINESS_TIMEZONE", "Asia/Kolkata")

# ── OTP ──────────────────────────────────────────────────
OTP_TTL_MINUTES = _int("OTP_TTL_MINUTES", 10)
OTP_MAX_ATTEMPTS = _int("OTP_MAX_ATTEMPTS", 5)
OTP_RESEND_COOLDOWN_SECONDS = _int("OTP_RESEND_COOLDOWN_SECONDS", 30)
OTP_MAX_PER_HOUR = _int("OTP_MAX_PER_HOUR", 5)
PASSWORD_RESET_TOKEN_TTL_MINUTES = _int("PASSWORD_RESET_TOKEN_TTL_MINUTES", 10)

# No SMS gateway is wired up yet. Outside production the OTP is echoed back in
# the API response so the apps can be used; production never does this.
OTP_ECHO_IN_RESPONSE = _bool("OTP_ECHO_IN_RESPONSE", not IS_PRODUCTION) and not IS_PRODUCTION

# ── Login brute-force protection (stored on the account row) ─
LOGIN_MAX_FAILED_ATTEMPTS = _int("LOGIN_MAX_FAILED_ATTEMPTS", 5)
LOGIN_LOCKOUT_MINUTES = _int("LOGIN_LOCKOUT_MINUTES", 15)

# ── Delivery / pickup codes ──────────────────────────────
DELIVERY_CODE_MAX_ATTEMPTS = _int("DELIVERY_CODE_MAX_ATTEMPTS", 5)

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

# ── Ordering windows ─────────────────────────────────────
EXTRA_ORDER_MAX_DAYS_AHEAD = _int("EXTRA_ORDER_MAX_DAYS_AHEAD", 9)
SUBSCRIPTION_MAX_START_DAYS_AHEAD = _int("SUBSCRIPTION_MAX_START_DAYS_AHEAD", 30)
CUSTOM_PLAN_MIN_DAYS = _int("CUSTOM_PLAN_MIN_DAYS", 1)
CUSTOM_PLAN_MAX_DAYS = _int("CUSTOM_PLAN_MAX_DAYS", 90)

# ── Uploads ──────────────────────────────────────────────
# Must be a persistent volume in production, otherwise images vanish on deploy.
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_UPLOAD_BYTES = _int("MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
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

    if problems:
        raise RuntimeError("Invalid configuration: " + "; ".join(problems))
