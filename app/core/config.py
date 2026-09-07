# ---------------------------------------------------------
# APPLICATION CONFIGURATION
# Loads all environment variables
# ---------------------------------------------------------

from dotenv import load_dotenv
import os

load_dotenv()

APP_NAME = os.getenv("APP_NAME")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not configured")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)

# Flat amount credited to a delivery boy's wallet per completed delivery.
DELIVERY_BOY_FEE_PER_DELIVERY = os.getenv(
    "DELIVERY_BOY_FEE_PER_DELIVERY",
    "30.00"
)
