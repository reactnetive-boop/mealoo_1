from pydantic import BaseModel




class CommonResponse(
    BaseModel
):

    success: bool
    message: str