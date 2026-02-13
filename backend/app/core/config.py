from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / '.env'), env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'FinanceSentiment'
    environment: str = 'dev'

    database_url: str = 'sqlite:///./backend/data/app.db'

    reddit_use_official_api: bool = True
    reddit_base_url: str = 'https://oauth.reddit.com'
    reddit_oauth_token_url: str = 'https://www.reddit.com/api/v1/access_token'
    reddit_client_id: str = Field(default='', validation_alias='REDDIT_CLIENT_ID')
    reddit_client_secret: str = Field(default='', validation_alias='REDDIT_CLIENT_SECRET')
    reddit_oauth_scope: str = 'read'
    reddit_user_agent: str = Field(
        default='financesentiment/0.1 (contact: email_or_repo)',
        validation_alias='REDDIT_USER_AGENT',
    )
    reddit_timeout_connect: float = 3.0
    reddit_timeout_read: float = 20.0
    reddit_max_concurrency: int = 1
    reddit_max_requests_per_minute: int = 90
    reddit_max_retries: int = 4
    reddit_backoff_base: float = 1.25
    reddit_min_request_interval_seconds: float = 0.7
    reddit_proxy_urls_csv: str = ''
    reddit_proxy_rotation_mode: str = 'round_robin'
    reddit_proxy_failure_cooldown_seconds: float = 180.0
    reddit_proxy_include_direct_fallback: bool = True
    reddit_thread_limit: int = 500
    reddit_thread_depth: int = 32
    reddit_morechildren_chunk_size: int = 100
    reddit_morechildren_max_batches: int = 40

    subreddits_csv: str = 'wallstreetbets,stocks,investing,finance'
    pull_sort: str = 'top'
    pull_t_param: str = 'day'
    pull_limit: int = 20
    pull_max_pages: int = 1
    pull_subreddit_pause_seconds: float = 2.0

    enable_external_extraction: bool = False
    extraction_text_cap: int = 50000

    download_images: bool = False
    image_max_size_bytes: int = 8_000_000

    use_finbert: bool = False
    use_llm_model: bool = False
    gemini_api_key: str = Field(default='', validation_alias='GEMINI_API_KEY')
    gemini_model: str = 'gemini-3-flash-preview'
    gemini_api_base_url: str = 'https://generativelanguage.googleapis.com/v1beta'
    llm_timeout_seconds: float = 12.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.0
    llm_max_output_tokens: int = 120
    llm_unclear_only: bool = True
    llm_low_confidence_threshold: float = 0.65
    llm_enable_sarcasm_trigger: bool = True
    llm_input_price_per_million_tokens: float = 0.15
    llm_output_price_per_million_tokens: float = 0.60
    unclear_threshold: float = 0.55
    unclear_short_text_len: int = 20
    inherit_parent_tickers_for_comments: bool = False
    inherit_title_tickers_for_comments: bool = False
    allow_context_label_inference: bool = False

    use_depth_decay: bool = True
    lambda_depth: float = 0.15
    use_time_decay: bool = False
    lambda_time: float = 0.05

    frontend_origin: str = 'http://localhost:3000'
    frontend_origins_csv: str = 'http://localhost:3000,http://127.0.0.1:3000'

    ticker_master_path: str = 'tickers_sample.csv'
    synonyms_path: str = 'synonyms.json'
    stoplist_path: str = 'stoplist.json'
    evaluation_dataset_path: str = 'gold_labels_sample.csv'
    evaluation_default_max_rows: int = 5000

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def backend_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def data_dir(self) -> Path:
        return self.backend_root / 'data'

    @property
    def resolved_database_url(self) -> str:
        if self.database_url.startswith('sqlite:///./'):
            rel_path = self.database_url.removeprefix('sqlite:///./')
            absolute_path = (self.repo_root / rel_path).resolve()
            absolute_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{absolute_path.as_posix()}"
        return self.database_url

    @property
    def image_root(self) -> Path:
        return self.repo_root / 'data' / 'images'

    @property
    def subreddits(self) -> list[str]:
        return [s.strip() for s in self.subreddits_csv.split(',') if s.strip()]

    @property
    def reddit_proxy_urls(self) -> list[str]:
        raw = [s.strip() for s in self.reddit_proxy_urls_csv.split(',') if s.strip()]
        seen: set[str] = set()
        out: list[str] = []
        for proxy_url in raw:
            if proxy_url in seen:
                continue
            seen.add(proxy_url)
            out.append(proxy_url)
        return out

    @property
    def frontend_origins(self) -> list[str]:
        raw = [s.strip() for s in self.frontend_origins_csv.split(',') if s.strip()]
        if self.frontend_origin and self.frontend_origin not in raw:
            raw.append(self.frontend_origin)
        seen: set[str] = set()
        out: list[str] = []
        for origin in raw:
            if origin in seen:
                continue
            seen.add(origin)
            out.append(origin)
        return out

    @property
    def ticker_master_file(self) -> Path:
        return self.repo_root / self.ticker_master_path

    @property
    def synonyms_file(self) -> Path:
        return self.repo_root / self.synonyms_path

    @property
    def stoplist_file(self) -> Path:
        return self.repo_root / self.stoplist_path

    @property
    def evaluation_dataset_file(self) -> Path:
        return self.repo_root / self.evaluation_dataset_path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
