# ---------------------------------------------------------
# MAIN APPLICATION ENTRY POINT
# ---------------------------------------------------------

from fastapi import FastAPI

from app.core.config import APP_NAME

app = FastAPI(
    title=APP_NAME
)


@app.get("/")
def health_check():

    return {
        "success": True,
        "message": f"{APP_NAME} Running Successfully"
    }