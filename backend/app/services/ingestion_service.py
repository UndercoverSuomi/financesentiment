from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.comment import Comment
from app.models.daily_score import DailyScore
from app.models.external_content import ExternalContent
from app.models.image import Image
from app.models.mention import Mention
from app.models.pull_run import PullRun
from app.models.stance import Stance
from app.models.submission import Submission
from app.schemas.common import TargetType
from app.services.aggregation_service import AggregationRecord, compute_daily_scores
from app.services.external_extractor import ExternalExtractor
from app.services.image_service import ImageService
from app.services.reddit_client import RedditClient
from app.services.reddit_parser import parse_listing_posts, parse_thread
from app.services.stance_service import StanceService
from app.services.ticker_extractor import TickerExtractor
from app.utils.timezone import to_berlin_date, utc_now


@dataclass(slots=True)
class PullExecutionResult:
    pull_run_id: int
    subreddit: str
    date_bucket_berlin: date
    status: str
    submissions: int
    comments: int
    mentions: int
    stance_rows: int
    error: str | None = None


class IngestionService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ticker_extractor = TickerExtractor(settings)
        self._stance_service = StanceService(settings, self._ticker_extractor)
        self._external_extractor = ExternalExtractor(settings)
        self._image_service = ImageService(settings)

    async def pull_subreddit(self, session: Session, subreddit: str) -> PullExecutionResult:
        async with RedditClient(self._settings) as reddit_client:
            reddit_client.reset_run_cache()
            return await self._pull_with_client(session=session, subreddit=subreddit, reddit_client=reddit_client)

    async def pull_all(self, session: Session) -> list[PullExecutionResult]:
        results: list[PullExecutionResult] = []
        async with RedditClient(self._settings) as reddit_client:
            for subreddit in self._settings.subreddits:
                reddit_client.reset_run_cache()
                results.append(
                    await self._pull_with_client(
                        session=session,
                        subreddit=subreddit,
                        reddit_client=reddit_client,
                    )
                )
        return results

    async def _pull_with_client(self, session: Session, subreddit: str, reddit_client: RedditClient) -> PullExecutionResult:
        pulled_at = utc_now()
        date_bucket = to_berlin_date(pulled_at)
        pull_run = PullRun(
            pulled_at_utc=pulled_at,
            date_bucket_berlin=date_bucket,
            subreddit=subreddit,
            sort=self._settings.pull_sort,
            t_param=self._settings.pull_t_param,
            limit=self._settings.pull_limit,
            status='running',
            error=None,
        )
        session.add(pull_run)
        session.commit()
        session.refresh(pull_run)

        submissions_count = 0
        comments_count = 0
        mentions_count = 0
        stance_rows_count = 0

        try:
            listing_payload = await reddit_client.get_top_listing(
                subreddit=subreddit,
                sort=self._settings.pull_sort,
                t_param=self._settings.pull_t_param,
                limit=self._settings.pull_limit,
            )
            parsed_submissions = parse_listing_posts(listing_payload)

            for parsed_submission in parsed_submissions:
                submission = self._upsert_submission(session, parsed_submission, pull_run.id)
                submissions_count += 1

                thread_payload = await reddit_client.get_thread(parsed_submission.id)
                _, parsed_comments = parse_thread(thread_payload)
                comments_count += len(parsed_comments)

                comment_ids = [c.id for c in parsed_comments]
                existing_comment_ids = self._comment_ids_for_submission(session, submission.id)
                all_comment_ids = sorted(existing_comment_ids.union(comment_ids))

                self._clear_analysis_rows(session, submission.id, all_comment_ids)

                stale_comment_ids = sorted(existing_comment_ids.difference(comment_ids))
                self._delete_comments(session, stale_comment_ids)

                parent_lookup = {c.id: c.body for c in parsed_comments}
                for parsed_comment in parsed_comments:
                    self._upsert_comment(session, parsed_comment)

                submission_mentions, submission_stance = self._analyze_submission(session, submission)
                mentions_count += submission_mentions
                stance_rows_count += submission_stance

                comment_mentions, comment_stance = self._analyze_comments(
                    session=session,
                    submission=submission,
                    parsed_comments=parsed_comments,
                    parent_lookup=parent_lookup,
                )
                mentions_count += comment_mentions
                stance_rows_count += comment_stance

                if self._settings.enable_external_extraction and self._is_external_url(submission.url):
                    extraction = await self._external_extractor.extract(submission.url)
                    self._upsert_external_content(
                        session=session,
                        submission_id=submission.id,
                        url=submission.url,
                        title=extraction.title,
                        text=extraction.text,
                        status=extraction.status,
                    )

                await self._store_images(session, submission, parsed_submission.raw, str(date_bucket))
                session.commit()

            self._recompute_daily_scores(session=session, date_bucket=date_bucket, subreddit=subreddit)

            pull_run.status = 'success'
            pull_run.error = None
            session.add(pull_run)
            session.commit()

            return PullExecutionResult(
                pull_run_id=pull_run.id,
                subreddit=subreddit,
                date_bucket_berlin=date_bucket,
                status='success',
                submissions=submissions_count,
                comments=comments_count,
                mentions=mentions_count,
                stance_rows=stance_rows_count,
            )
        except Exception as exc:
            session.rollback()
            run = session.get(PullRun, pull_run.id)
            if run:
                run.status = 'failed'
                run.error = str(exc)[:4000]
                session.add(run)
                session.commit()
            return PullExecutionResult(
                pull_run_id=pull_run.id,
                subreddit=subreddit,
                date_bucket_berlin=date_bucket,
                status='failed',
                submissions=submissions_count,
                comments=comments_count,
                mentions=mentions_count,
                stance_rows=stance_rows_count,
                error=str(exc),
            )

    def _upsert_submission(self, session: Session, parsed_submission, pull_run_id: int) -> Submission:
        row = session.get(Submission, parsed_submission.id)
        if row is None:
            row = Submission(
                id=parsed_submission.id,
                subreddit=parsed_submission.subreddit,
                created_utc=parsed_submission.created_utc,
                title=parsed_submission.title,
                selftext=parsed_submission.selftext,
                url=parsed_submission.url,
                score=parsed_submission.score,
                num_comments=parsed_submission.num_comments,
                permalink=parsed_submission.permalink,
                pull_run_id=pull_run_id,
            )
            session.add(row)
            session.flush()
            return row

        row.subreddit = parsed_submission.subreddit
        row.created_utc = parsed_submission.created_utc
        row.title = parsed_submission.title
        row.selftext = parsed_submission.selftext
        row.url = parsed_submission.url
        row.score = parsed_submission.score
        row.num_comments = parsed_submission.num_comments
        row.permalink = parsed_submission.permalink
        row.pull_run_id = pull_run_id
        session.add(row)
        session.flush()
        return row

    def _upsert_comment(self, session: Session, parsed_comment) -> Comment:
        row = session.get(Comment, parsed_comment.id)
        if row is None:
            row = Comment(
                id=parsed_comment.id,
                submission_id=parsed_comment.submission_id,
                parent_id=parsed_comment.parent_id,
                depth=parsed_comment.depth,
                author=parsed_comment.author,
                created_utc=parsed_comment.created_utc,
                score=parsed_comment.score,
                body=parsed_comment.body,
                permalink=parsed_comment.permalink,
            )
            session.add(row)
            return row

        row.submission_id = parsed_comment.submission_id
        row.parent_id = parsed_comment.parent_id
        row.depth = parsed_comment.depth
        row.author = parsed_comment.author
        row.created_utc = parsed_comment.created_utc
        row.score = parsed_comment.score
        row.body = parsed_comment.body
        row.permalink = parsed_comment.permalink
        session.add(row)
        return row

    def _clear_analysis_rows(self, session: Session, submission_id: str, comment_ids: list[str]) -> None:
        session.execute(
            delete(Mention).where(and_(Mention.target_type == 'submission', Mention.target_id == submission_id))
        )
        session.execute(
            delete(Stance).where(and_(Stance.target_type == 'submission', Stance.target_id == submission_id))
        )

        if comment_ids:
            session.execute(
                delete(Mention).where(and_(Mention.target_type == 'comment', Mention.target_id.in_(comment_ids)))
            )
            session.execute(
                delete(Stance).where(and_(Stance.target_type == 'comment', Stance.target_id.in_(comment_ids)))
            )

    def _comment_ids_for_submission(self, session: Session, submission_id: str) -> set[str]:
        rows = session.execute(
            select(Comment.id).where(Comment.submission_id == submission_id)
        ).scalars().all()
        return set(rows)

    def _delete_comments(self, session: Session, comment_ids: list[str]) -> None:
        if not comment_ids:
            return
        session.execute(
            delete(Comment).where(Comment.id.in_(comment_ids))
        )

    def _analyze_submission(self, session: Session, submission: Submission) -> tuple[int, int]:
        mentions_count = 0
        stance_count = 0
        text = f'{submission.title}\n{submission.selftext}'.strip()

        results = self._stance_service.analyze_target(
            target_type=TargetType.submission,
            text=text,
            title=submission.title,
            selftext=submission.selftext,
            parent_text='',
        )
        for r in results:
            session.add(
                Mention(
                    target_type='submission',
                    target_id=submission.id,
                    ticker=r.mention.ticker,
                    confidence=r.mention.confidence,
                    source=r.mention.source,
                    span_start=r.mention.span_start,
                    span_end=r.mention.span_end,
                )
            )
            session.add(
                Stance(
                    target_type='submission',
                    target_id=submission.id,
                    ticker=r.mention.ticker,
                    stance_label=r.label.value,
                    stance_score=r.score,
                    confidence=r.confidence,
                    model_version=r.model_version,
                    context_text=r.context_text,
                )
            )
            mentions_count += 1
            stance_count += 1
        return mentions_count, stance_count

    def _analyze_comments(
        self,
        session: Session,
        submission: Submission,
        parsed_comments: list,
        parent_lookup: dict[str, str],
    ) -> tuple[int, int]:
        mentions_count = 0
        stance_count = 0

        for c in parsed_comments:
            parent_text = parent_lookup.get(c.parent_id or '', '')
            results = self._stance_service.analyze_target(
                target_type=TargetType.comment,
                text=c.body,
                title=submission.title,
                selftext=submission.selftext,
                parent_text=parent_text,
            )
            for r in results:
                session.add(
                    Mention(
                        target_type='comment',
                        target_id=c.id,
                        ticker=r.mention.ticker,
                        confidence=r.mention.confidence,
                        source=r.mention.source,
                        span_start=r.mention.span_start,
                        span_end=r.mention.span_end,
                    )
                )
                session.add(
                    Stance(
                        target_type='comment',
                        target_id=c.id,
                        ticker=r.mention.ticker,
                        stance_label=r.label.value,
                        stance_score=r.score,
                        confidence=r.confidence,
                        model_version=r.model_version,
                        context_text=r.context_text,
                    )
                )
                mentions_count += 1
                stance_count += 1
        return mentions_count, stance_count

    def _upsert_external_content(
        self,
        session: Session,
        submission_id: str,
        url: str,
        title: str,
        text: str,
        status: str,
    ) -> None:
        row = session.execute(
            select(ExternalContent).where(ExternalContent.submission_id == submission_id)
        ).scalar_one_or_none()
        if row is None:
            row = ExternalContent(
                submission_id=submission_id,
                external_url=url,
                title=title,
                text=text,
                status=status,
                fetched_at=utc_now(),
            )
        else:
            row.external_url = url
            row.title = title
            row.text = text
            row.status = status
            row.fetched_at = utc_now()
        session.add(row)

    async def _store_images(self, session: Session, submission: Submission, raw_submission: dict, date_bucket: str) -> None:
        session.execute(
            delete(Image).where(Image.submission_id == submission.id)
        )

        candidates = self._image_service.collect_candidates(raw_submission)
        if not candidates:
            return

        for candidate in candidates:
            download = await self._image_service.download_if_enabled(candidate.url, date_bucket, submission.id)
            session.add(
                Image(
                    submission_id=submission.id,
                    image_url=candidate.url,
                    local_path=download.local_path,
                    width=candidate.width,
                    height=candidate.height,
                    status=download.status,
                )
            )

    def _recompute_daily_scores(self, session: Session, date_bucket: date, subreddit: str) -> None:
        submissions = session.execute(
            select(Submission)
            .join(PullRun, PullRun.id == Submission.pull_run_id)
            .where(PullRun.date_bucket_berlin == date_bucket, PullRun.subreddit == subreddit)
        ).scalars().all()

        submission_ids = [s.id for s in submissions]
        if not submission_ids:
            return

        comments = session.execute(
            select(Comment).where(Comment.submission_id.in_(submission_ids))
        ).scalars().all()

        submission_meta = {
            s.id: {'score': s.score, 'depth': 0, 'created_utc': s.created_utc}
            for s in submissions
        }
        comment_meta = {
            c.id: {'score': c.score, 'depth': c.depth, 'created_utc': c.created_utc}
            for c in comments
        }

        comment_ids = list(comment_meta.keys())
        stance_rows = session.execute(
            select(Stance).where(
                or_(
                    and_(Stance.target_type == 'submission', Stance.target_id.in_(submission_ids)),
                    and_(Stance.target_type == 'comment', Stance.target_id.in_(comment_ids or ['__none__'])),
                )
            )
        ).scalars().all()

        records: list[AggregationRecord] = []
        for stance in stance_rows:
            if stance.target_type == 'submission':
                meta = submission_meta.get(stance.target_id)
            else:
                meta = comment_meta.get(stance.target_id)
            if not meta:
                continue
            records.append(
                AggregationRecord(
                    ticker=stance.ticker,
                    stance_label=stance.stance_label,
                    stance_score=stance.stance_score,
                    upvote_score=int(meta['score']),
                    depth=int(meta['depth']),
                    created_utc=meta['created_utc'],
                )
            )

        metrics_by_ticker = compute_daily_scores(
            records,
            use_depth_decay=self._settings.use_depth_decay,
            lambda_depth=self._settings.lambda_depth,
            use_time_decay=self._settings.use_time_decay,
            lambda_time=self._settings.lambda_time,
            reference_time=utc_now(),
        )

        session.execute(
            delete(DailyScore).where(
                and_(
                    DailyScore.date_bucket_berlin == date_bucket,
                    DailyScore.subreddit == subreddit,
                )
            )
        )

        for ticker, metrics in metrics_by_ticker.items():
            session.add(
                DailyScore(
                    date_bucket_berlin=date_bucket,
                    subreddit=subreddit,
                    ticker=ticker,
                    score_unweighted=metrics.score_unweighted,
                    score_weighted=metrics.score_weighted,
                    mention_count=metrics.mention_count,
                    bullish_count=metrics.bullish_count,
                    bearish_count=metrics.bearish_count,
                    neutral_count=metrics.neutral_count,
                    unclear_count=metrics.unclear_count,
                    unclear_rate=metrics.unclear_rate,
                )
            )

        session.commit()

    def _is_external_url(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        if not host:
            return False
        return 'reddit.com' not in host and 'redd.it' not in host
