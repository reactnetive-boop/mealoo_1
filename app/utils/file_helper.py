import os
import uuid

from fastapi import UploadFile


UPLOAD_DIR = (
    "uploads/providers/profile"
)

os.makedirs(
    UPLOAD_DIR,
    exist_ok=True
)


def save_profile_image(
    file: UploadFile
):

    file_extension = (
        file.filename.split(".")[-1]
    )

    unique_filename = (
        f"{uuid.uuid4()}.{file_extension}"
    )

    file_path = (
        f"{UPLOAD_DIR}/{unique_filename}"
    )

    with open(file_path, "wb") as buffer:

        buffer.write(
            file.file.read()
        )

    return file_path