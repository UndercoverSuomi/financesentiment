from __future__ import annotations

import hashlib
import html
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import Settings

IMAGE_EXT_RE = re.compile(r'\.(?:jpe?g|png|webp)(?:\?|$)', re.IGNORECASE)
ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp'}


@dataclass(slots=True)
class ImageCandidate:
    url: str
    width: int | None
    height: int | None


@dataclass(slots=True)
class ImageDownloadResult:
    local_path: str | None
    status: str


class ImageService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def collect_candidates(self, submission_data: dict) -> list[ImageCandidate]:
        seen: set[str] = set()
        output: list[ImageCandidate] = []

        url = str(submission_data.get('url', ''))
        if IMAGE_EXT_RE.search(url):
            clean_url = html.unescape(url)
            seen.add(clean_url)
            output.append(ImageCandidate(url=clean_url, width=None, height=None))

        preview = submission_data.get('preview', {})
        images = preview.get('images', []) if isinstance(preview, dict) else []
        for item in images:
            source = item.get('source', {}) if isinstance(item, dict) else {}
            src = source.get('url')
            if not src:
                continue
            clean_url = html.unescape(str(src))
            if clean_url in seen:
                continue
            seen.add(clean_url)
            output.append(
                ImageCandidate(
                    url=clean_url,
                    width=int(source.get('width')) if source.get('width') else None,
                    height=int(source.get('height')) if source.get('height') else None,
                )
            )

        return output

    async def download_if_enabled(self, url: str, date_bucket: str, submission_id: str) -> ImageDownloadResult:
        if not self._settings.download_images:
            return ImageDownloadResult(local_path=None, status='download_disabled')

        folder = self._settings.image_root / date_bucket / submission_id
        folder.mkdir(parents=True, exist_ok=True)

        timeout = httpx.Timeout(connect=3.0, read=8.0, write=8.0, pool=8.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={'User-Agent': self._settings.reddit_user_agent}) as client:
                async with client.stream('GET', url) as resp:
                    if resp.status_code >= 400:
                        return ImageDownloadResult(local_path=None, status=f'http_{resp.status_code}')

                    ctype = (resp.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()
                    if ctype not in ALLOWED_TYPES:
                        return ImageDownloadResult(local_path=None, status='content_type_blocked')

                    clen = resp.headers.get('Content-Length')
                    if clen and int(clen) > self._settings.image_max_size_bytes:
                        return ImageDownloadResult(local_path=None, status='too_large')

                    ext = _ext_from_content_type(ctype) or _ext_from_url(url)
                    file_id = hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]
                    file_name = f'{file_id}{ext}'
                    target = folder / file_name

                    total = 0
                    with target.open('wb') as f:
                        async for chunk in resp.aiter_bytes():
                            total += len(chunk)
                            if total > self._settings.image_max_size_bytes:
                                f.close()
                                if target.exists():
                                    os.remove(target)
                                return ImageDownloadResult(local_path=None, status='too_large')
                            f.write(chunk)

            return ImageDownloadResult(local_path=str(target.relative_to(self._settings.repo_root)), status='downloaded')
        except Exception:
            return ImageDownloadResult(local_path=None, status='download_failed')


def _ext_from_content_type(content_type: str) -> str | None:
    return {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
    }.get(content_type)


def _ext_from_url(url: str) -> str:
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    if ext in {'.jpg', '.jpeg', '.png', '.webp'}:
        return ext
    return '.img'
