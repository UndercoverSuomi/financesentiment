from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.utils.text import clamp_text, normalize_text


@dataclass(slots=True)
class ExtractionResult:
    title: str
    text: str
    status: str


class ExternalExtractor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def extract(self, url: str) -> ExtractionResult:
        timeout = httpx.Timeout(connect=3.0, read=8.0, write=8.0, pool=8.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={'User-Agent': self._settings.reddit_user_agent}) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text
        except Exception:
            return ExtractionResult(title='', text='', status='fetch_failed')

        text = ''
        title = ''

        try:
            import trafilatura

            extracted = trafilatura.extract(html)
            if extracted:
                text = extracted
                status = 'ok_trafilatura'
            else:
                status = 'trafilatura_empty'
        except Exception:
            status = 'trafilatura_failed'

        if not text:
            try:
                from bs4 import BeautifulSoup
                from readability import Document

                doc = Document(html)
                title = doc.short_title() or ''
                summary = doc.summary() or ''
                text = BeautifulSoup(summary, 'html.parser').get_text(' ', strip=True)
                if text:
                    status = 'ok_readability'
            except Exception:
                status = f'{status}_readability_failed'

        return ExtractionResult(
            title=normalize_text(title),
            text=clamp_text(normalize_text(text), self._settings.extraction_text_cap),
            status=status,
        )
