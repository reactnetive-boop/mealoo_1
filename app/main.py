# ---------------------------------------------------------
# MAIN APPLICATION ENTRY POINT
# ---------------------------------------------------------

from fastapi import FastAPI

from app.core.config import APP_NAME
from app.api.v1.api import api_router
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title=APP_NAME
)


@app.get("/")
def health_check():

    return {
        "success": True,
        "message": f"{APP_NAME} Running Successfully"
    }

app.include_router(
    api_router,
    prefix="/api/v1"
)

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)