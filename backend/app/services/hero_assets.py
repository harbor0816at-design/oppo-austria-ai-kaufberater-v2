from __future__ import annotations

import uuid
from dataclasses import dataclass


class HeroAssetError(RuntimeError):
    pass


class HeroAssetConfigurationError(HeroAssetError):
    pass


class HeroAssetValidationError(HeroAssetError):
    pass


class HeroAssetUploadError(HeroAssetError):
    pass


@dataclass(frozen=True)
class UploadedHeroAsset:
    url: str
    pathname: str


class HeroAssetStorage:
    max_upload_bytes = 4 * 1024 * 1024
    _extensions = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }

    def __init__(self, token: str | None):
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @classmethod
    def _validate(cls, content: bytes, content_type: str | None) -> tuple[str, str]:
        if not content:
            raise HeroAssetValidationError("The uploaded image is empty")
        if len(content) > cls.max_upload_bytes:
            raise HeroAssetValidationError("Hero images must be 4 MB or smaller")
        extension = cls._extensions.get(content_type or "")
        if extension is None:
            raise HeroAssetValidationError("Only JPEG, PNG, and WebP hero images are supported")

        signatures = {
            "image/jpeg": content.startswith(b"\xff\xd8\xff"),
            "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP",
        }
        if not signatures[content_type]:
            raise HeroAssetValidationError("The file content does not match its image type")
        return extension, content_type

    async def upload(self, content: bytes, content_type: str | None) -> UploadedHeroAsset:
        extension, verified_type = self._validate(content, content_type)
        if not self.token:
            raise HeroAssetConfigurationError("BLOB_READ_WRITE_TOKEN is not configured")

        try:
            from vercel.blob import AsyncBlobClient

            pathname = f"oppo-austria/hero/{uuid.uuid4().hex}.{extension}"
            async with AsyncBlobClient(token=self.token) as client:
                blob = await client.put(
                    pathname,
                    content,
                    access="public",
                    content_type=verified_type,
                )
            return UploadedHeroAsset(url=blob.url, pathname=blob.pathname)
        except HeroAssetError:
            raise
        except Exception as exc:
            raise HeroAssetUploadError("Vercel Blob upload failed") from exc
