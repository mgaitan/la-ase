from __future__ import annotations

from datetime import UTC, datetime
import io
import os
from pathlib import Path
import secrets

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from app.settings import load_env_file


load_env_file()

R2_ACCOUNT_ID_ENV = "R2_ACCOUNT_ID"
R2_BUCKET_NAME_ENV = "R2_BUCKET_NAME"
R2_ACCESS_KEY_ID_ENV = "R2_ACCESS_KEY_ID"
R2_SECRET_ACCESS_KEY_ENV = "R2_SECRET_ACCESS_KEY"

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1280


class StorageNotConfiguredError(RuntimeError):
    pass


class StorageUploadError(RuntimeError):
    pass


def _resize_frame(frame: Image.Image) -> Image.Image:
    resized = ImageOps.exif_transpose(frame)
    if max(resized.size) <= MAX_IMAGE_DIMENSION:
        return resized
    resized.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
    return resized


def _normalize_image(content: bytes, content_type: str) -> bytes:
    try:
        with Image.open(io.BytesIO(content)) as image:
            if content_type == "image/gif":
                frames: list[Image.Image] = []
                durations: list[int] = []
                for frame in ImageSequence.Iterator(image):
                    resized = _resize_frame(frame.copy().convert("RGBA"))
                    frames.append(resized)
                    durations.append(frame.info.get("duration", image.info.get("duration", 100)))

                if not frames:
                    raise StorageUploadError("No se pudo procesar la imagen.")

                output = io.BytesIO()
                frames[0].save(
                    output,
                    format="GIF",
                    save_all=True,
                    append_images=frames[1:],
                    loop=image.info.get("loop", 0),
                    duration=durations,
                    optimize=True,
                )
                return output.getvalue()

            resized = _resize_frame(image.copy())
            output = io.BytesIO()
            save_kwargs: dict[str, object] = {}

            if content_type == "image/jpeg":
                resized = resized.convert("RGB")
                save_kwargs = {"format": "JPEG", "quality": 85, "optimize": True}
            elif content_type == "image/png":
                save_kwargs = {"format": "PNG", "optimize": True}
            elif content_type == "image/webp":
                save_kwargs = {"format": "WEBP", "quality": 85, "method": 6}

            resized.save(output, **save_kwargs)
            return output.getvalue()
    except UnidentifiedImageError as exc:
        raise StorageUploadError("El archivo subido no es una imagen valida.") from exc

    raise StorageUploadError("No se pudo procesar la imagen.")


def is_r2_configured() -> bool:
    return all(
        os.getenv(name)
        for name in (
            R2_ACCOUNT_ID_ENV,
            R2_BUCKET_NAME_ENV,
            R2_ACCESS_KEY_ID_ENV,
            R2_SECRET_ACCESS_KEY_ENV,
        )
    )


def _require(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise StorageNotConfiguredError(
        f"Missing required storage environment variable: {name}"
    )


def get_r2_client():
    account_id = _require(R2_ACCOUNT_ID_ENV)
    access_key_id = _require(R2_ACCESS_KEY_ID_ENV)
    secret_access_key = _require(R2_SECRET_ACCESS_KEY_ENV)
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def get_bucket_name() -> str:
    return _require(R2_BUCKET_NAME_ENV)


def upload_image(*, content: bytes, content_type: str, filename: str | None = None) -> str:
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise StorageUploadError("Formato no permitido. Usa JPG, PNG, WEBP o GIF.")

    content = _normalize_image(content, content_type)
    if len(content) > MAX_IMAGE_SIZE:
        raise StorageUploadError("La imagen procesada supera el límite de 8 MB.")

    suffix = ALLOWED_IMAGE_TYPES[content_type]
    original_stem = Path(filename or "imagen").stem
    safe_stem = "".join(char for char in original_stem.lower() if char.isalnum() or char in {"-", "_"})
    safe_stem = safe_stem[:40] or "imagen"
    date_path = datetime.now(UTC).strftime("%Y/%m")
    key = f"uploads/{date_path}/{safe_stem}-{secrets.token_hex(8)}{suffix}"

    try:
        get_r2_client().put_object(
            Bucket=get_bucket_name(),
            Key=key,
            Body=content,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUploadError("No se pudo subir la imagen a R2.") from exc

    return key


def fetch_object(key: str) -> tuple[io.BytesIO, str]:
    try:
        response = get_r2_client().get_object(Bucket=get_bucket_name(), Key=key)
    except (BotoCoreError, ClientError) as exc:
        raise StorageUploadError("No se pudo recuperar la imagen.") from exc

    body = response["Body"].read()
    content_type = response.get("ContentType", "application/octet-stream")
    return io.BytesIO(body), content_type
