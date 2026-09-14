# ---------------------------------------------------------
# APPLICATION CONFIGURATION
# Loads all environment variables
# ---------------------------------------------------------

from dotenv import load_dotenv
import os

load_dotenv()

APP_NAME = os.getenv("APP_NAME")

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
)

# Flat amount credited to a delivery boy's wallet per completed delivery.
DELIVERY_BOY_FEE_PER_DELIVERY = os.getenv(
    "DELIVERY_BOY_FEE_PER_DELIVERY",
    "30.00"
)
