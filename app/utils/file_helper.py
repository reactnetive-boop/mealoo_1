import os
import uuid

from fastapi import UploadFile


PROFILE_UPLOAD_DIR = (
    "uploads/providers/profile"
)

USER_PROFILE_UPLOAD_DIR = (
    "uploads/users/profile"
)

PACKAGE_UPLOAD_DIR = (
    "uploads/package_images"
)

DELIVERY_DOCUMENT_UPLOAD_DIR = (
    "uploads/delivery_boys/documents"
)

os.makedirs(
    PROFILE_UPLOAD_DIR,
    exist_ok=True
)

os.makedirs(
    USER_PROFILE_UPLOAD_DIR,
    exist_ok=True
)

os.makedirs(
    PACKAGE_UPLOAD_DIR,
    exist_ok=True
)

os.makedirs(
    DELIVERY_DOCUMENT_UPLOAD_DIR,
    exist_ok=True
)


def save_profile_image(
    file: UploadFile
):

    return save_file(
        file=file,
        upload_dir=PROFILE_UPLOAD_DIR
    )


def save_user_profile_image(
    file: UploadFile
):

    return save_file(
        file=file,
        upload_dir=USER_PROFILE_UPLOAD_DIR
    )


def save_package_image(
    file: UploadFile
):

    return save_file(
        file=file,
        upload_dir=PACKAGE_UPLOAD_DIR
    )


def save_delivery_document(
    file: UploadFile
):

    return save_file(
        file=file,
        upload_dir=DELIVERY_DOCUMENT_UPLOAD_DIR
    )


def save_file(
    file: UploadFile,
    upload_dir: str
):

    file_extension = (
        file.filename.split(".")[-1]
    )

    unique_filename = (
        f"{uuid.uuid4()}.{file_extension}"
    )

    file_path = (
        f"{upload_dir}/{unique_filename}"
    )

    with open(
        file_path,
        "wb"
    ) as buffer:

        buffer.write(
            file.file.read()
        )

    return file_path