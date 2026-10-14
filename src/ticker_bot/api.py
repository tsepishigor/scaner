from __future__ import annotations

import hmac
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Annotated, Self

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from ticker_bot import __version__
from ticker_bot.config import Settings
from ticker_bot.criteria import ScannerCriteria, evaluate_criteria
from ticker_bot.database import TickerDatabase, TickerSummary
from ticker_bot.extractor import TickerExtractor
from ticker_bot.ingestion import TickerIngestionService
from ticker_bot.market_data import DemoMarketDataProvider
from ticker_bot.telegram_bot import TelegramBotService

_STATIC_DIR = Path(__file__).parent / "static"
_TICKER_RE = re.compile(r"^[A-Z]{1,6}(?:\.[A-Z]{1,2})?$")


class TickerItem(BaseModel):
    ticker: str
    mentions: int
    first_seen_utc: datetime
    last_seen_utc: datetime


class TickerListResponse(BaseModel):
    date: date
    timezone: str
    chat_id: int | None
    unique_tickers: int
    total_mentions: int
    items: list[TickerItem]


class CriteriaPayload(BaseModel):
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    min_change_percent: float | None = Field(default=None, ge=-100, le=1000)
    min_volume: int | None = Field(default=None, ge=0)
    min_relative_volume: float | None = Field(default=None, ge=0)
    max_float_millions: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_price_range(self) -> Self:
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("Мінімальна ціна не може бути більшою за максимальну")
        return self

    def to_domain(self) -> ScannerCriteria:
        return ScannerCriteria(**self.model_dump())

    @classmethod
    def from_domain(cls, value: ScannerCriteria) -> CriteriaPayload:
        return cls(
            min_price=value.min_price,
            max_price=value.max_price,
            min_change_percent=value.min_change_percent,
            min_volume=value.min_volume,
            min_relative_volume=value.min_relative_volume,
            max_float_millions=value.max_float_millions,
        )


class MarketSnapshotResponse(BaseModel):
    price: float
    change_percent: float
    volume: int
    relative_volume: float
    float_millions: float
    market_cap_millions: float
    previous_close: float


class ScannerRowResponse(BaseModel):
    ticker: str
    mentions: int
    first_seen_utc: datetime
    last_seen_utc: datetime
    matches: bool
    failed_rules: list[str]
    rating: int | None
    notes: str
    market: MarketSnapshotResponse


class ScannerResponse(BaseModel):
    date: date
    timezone: str
    data_mode: str
    preview: bool
    active_criteria: int
    total_count: int
    matched_count: int
    items: list[ScannerRowResponse]


class ReviewInput(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    notes: str = Field(default="", max_length=4000)


class LoginInput(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ReviewResponse(BaseModel):
    date: date
    ticker: str
    rating: int | None
    notes: str
    updated_at_utc: datetime | None


class CandleResponse(BaseModel):
    timestamp_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class ChartResponse(BaseModel):
    ticker: str
    date: date
    interval: str
    data_mode: str
    candles: list[CandleResponse]


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper().replace("-", ".")
    if not _TICKER_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="Некоректний тікер")
    return normalized


def create_app(settings: Settings) -> FastAPI:
    database = TickerDatabase(settings.database_path)
    extractor = TickerExtractor(include_plain=settings.enable_plain_tickers)
    ingestion = TickerIngestionService(
        database=database,
        extractor=extractor,
        timezone_=settings.app_timezone,
    )
    market_data = DemoMarketDataProvider()
    telegram = (
        TelegramBotService(settings=settings, database=database, ingestion=ingestion)
        if settings.bot_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await database.initialize()
        app.state.database = database
        app.state.telegram = telegram
        try:
            if telegram is not None:
                await telegram.start()
            yield
        finally:
            if telegram is not None:
                await telegram.stop()

    app = FastAPI(
        title="Telegram Ticker Scanner",
        version=__version__,
        description="Telegram ticker collector and private stock scanner",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    def expected_session_cookie() -> str | None:
        password = settings.scanner_site_password
        if password is None:
            return None
        return hmac.digest(
            password.encode(),
            b"telegram-scanner-session-v1",
            "sha256",
        ).hex()

    public_paths = {"/login", "/api/session/login", "/healthz", "/readyz"}

    @app.middleware("http")
    async def require_site_login(request: Request, call_next):
        expected = expected_session_cookie()
        if expected is None or request.url.path in public_paths:
            return await call_next(request)

        supplied = request.cookies.get("scanner_session", "")
        if supplied and hmac.compare_digest(supplied, expected):
            return await call_next(request)

        if request.url.path == "/" or "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return JSONResponse(
            {"detail": "Потрібно увійти в сканер"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    async def require_api_token(authorization: str | None = Header(default=None)) -> None:
        expected = settings.scanner_api_token
        if expected is None:
            return
        prefix = "Bearer "
        supplied = (
            authorization[len(prefix) :]
            if authorization and authorization.startswith(prefix)
            else ""
        )
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def selected_day(day: date | None) -> date:
        return day or datetime.now(UTC).astimezone(settings.app_timezone).date()

    @app.get("/login", include_in_schema=False, response_model=None)
    async def login_page() -> FileResponse | RedirectResponse:
        if settings.scanner_site_password is None:
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        return FileResponse(_STATIC_DIR / "login.html")

    @app.post("/api/session/login", include_in_schema=False)
    async def login(payload: LoginInput, request: Request) -> JSONResponse:
        password = settings.scanner_site_password
        if password is None or not hmac.compare_digest(payload.password, password):
            return JSONResponse(
                {"detail": "Неправильний пароль"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        response = JSONResponse({"status": "ok"})
        forwarded_scheme = request.headers.get("x-forwarded-proto", "")
        response.set_cookie(
            key="scanner_session",
            value=expected_session_cookie(),
            httponly=True,
            secure=request.url.scheme == "https" or forwarded_scheme == "https",
            samesite="strict",
            max_age=60 * 60 * 12,
        )
        return response

    @app.get("/", include_in_schema=False)
    async def scanner_page() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/healthz")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            "bot_enabled": settings.bot_enabled,
            "bot_running": telegram.running if telegram is not None else False,
            "market_data": "demo",
        }

    @app.get("/readyz")
    async def readiness() -> dict[str, str]:
        if not await database.check():
            raise HTTPException(status_code=503, detail="Database is not ready")
        if telegram is not None and not telegram.running:
            raise HTTPException(status_code=503, detail="Telegram bot is not ready")
        return {"status": "ready"}

    @app.get(
        "/api/v1/tickers",
        response_model=TickerListResponse,
        dependencies=[Depends(require_api_token)],
    )
    async def list_tickers(
        day: Annotated[date | None, Query(description="Local day, YYYY-MM-DD")] = None,
        chat_id: int | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 500,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> TickerListResponse:
        requested_day = selected_day(day)
        rows = await database.list_tickers(
            local_date=requested_day,
            chat_id=chat_id,
            limit=limit,
            offset=offset,
        )
        stats = await database.day_stats(local_date=requested_day, chat_id=chat_id)
        return TickerListResponse(
            date=requested_day,
            timezone=str(settings.app_timezone),
            chat_id=chat_id,
            unique_tickers=stats.unique_tickers,
            total_mentions=stats.total_mentions,
            items=[
                TickerItem(
                    ticker=row.ticker,
                    mentions=row.mentions,
                    first_seen_utc=row.first_seen_utc,
                    last_seen_utc=row.last_seen_utc,
                )
                for row in rows
            ],
        )

    @app.get(
        "/api/v1/scanner",
        response_model=ScannerResponse,
        dependencies=[Depends(require_api_token)],
    )
    async def scanner_rows(
        day: date | None = None,
        only_matches: bool = False,
        preview_if_empty: bool = False,
    ) -> ScannerResponse:
        requested_day = selected_day(day)
        summaries = await database.list_tickers(local_date=requested_day, limit=500)
        is_preview = False
        if not summaries and preview_if_empty:
            is_preview = True
            preview_time = datetime.combine(requested_day, time(13, 30), tzinfo=UTC)
            summaries = [
                TickerSummary(symbol, 1, preview_time, preview_time)
                for symbol in ("AAPL", "NVDA", "TSLA", "PLTR", "AMD")
            ]

        criteria = await database.get_criteria()
        items: list[ScannerRowResponse] = []
        matched_count = 0
        for summary in summaries:
            snapshot = market_data.snapshot(summary.ticker, requested_day)
            result = evaluate_criteria(snapshot, criteria)
            if result.matches:
                matched_count += 1
            if only_matches and not result.matches:
                continue
            review = await database.get_review(
                local_date=requested_day,
                ticker=summary.ticker,
            )
            items.append(
                ScannerRowResponse(
                    ticker=summary.ticker,
                    mentions=summary.mentions,
                    first_seen_utc=summary.first_seen_utc,
                    last_seen_utc=summary.last_seen_utc,
                    matches=result.matches,
                    failed_rules=list(result.failed_rules),
                    rating=review.rating if review else None,
                    notes=review.notes if review else "",
                    market=MarketSnapshotResponse(
                        price=snapshot.price,
                        change_percent=snapshot.change_percent,
                        volume=snapshot.volume,
                        relative_volume=snapshot.relative_volume,
                        float_millions=snapshot.float_millions,
                        market_cap_millions=snapshot.market_cap_millions,
                        previous_close=snapshot.previous_close,
                    ),
                )
            )

        return ScannerResponse(
            date=requested_day,
            timezone=str(settings.app_timezone),
            data_mode="demo",
            preview=is_preview,
            active_criteria=criteria.active_count,
            total_count=len(summaries),
            matched_count=matched_count,
            items=items,
        )

    @app.get(
        "/api/v1/scanner/criteria",
        response_model=CriteriaPayload,
        dependencies=[Depends(require_api_token)],
    )
    async def get_criteria() -> CriteriaPayload:
        return CriteriaPayload.from_domain(await database.get_criteria())

    @app.put(
        "/api/v1/scanner/criteria",
        response_model=CriteriaPayload,
        dependencies=[Depends(require_api_token)],
    )
    async def save_criteria(payload: CriteriaPayload) -> CriteriaPayload:
        saved = await database.save_criteria(payload.to_domain())
        return CriteriaPayload.from_domain(saved)

    @app.get(
        "/api/v1/scanner/reviews/{ticker}",
        response_model=ReviewResponse,
        dependencies=[Depends(require_api_token)],
    )
    async def get_review(ticker: str, day: date | None = None) -> ReviewResponse:
        normalized = _normalize_ticker(ticker)
        requested_day = selected_day(day)
        review = await database.get_review(local_date=requested_day, ticker=normalized)
        return ReviewResponse(
            date=requested_day,
            ticker=normalized,
            rating=review.rating if review else None,
            notes=review.notes if review else "",
            updated_at_utc=review.updated_at_utc if review else None,
        )

    @app.put(
        "/api/v1/scanner/reviews/{ticker}",
        response_model=ReviewResponse,
        dependencies=[Depends(require_api_token)],
    )
    async def save_review(
        ticker: str,
        payload: ReviewInput,
        day: date | None = None,
    ) -> ReviewResponse:
        normalized = _normalize_ticker(ticker)
        requested_day = selected_day(day)
        review = await database.save_review(
            local_date=requested_day,
            ticker=normalized,
            rating=payload.rating,
            notes=payload.notes.strip(),
        )
        return ReviewResponse(
            date=review.local_date,
            ticker=review.ticker,
            rating=review.rating,
            notes=review.notes,
            updated_at_utc=review.updated_at_utc,
        )

    @app.get(
        "/api/v1/scanner/chart/{ticker}",
        response_model=ChartResponse,
        dependencies=[Depends(require_api_token)],
    )
    async def chart(
        ticker: str,
        day: date | None = None,
        interval: Annotated[str, Query(pattern="^(1|2|5|15|60|1D)$")] = "5",
    ) -> ChartResponse:
        normalized = _normalize_ticker(ticker)
        requested_day = selected_day(day)
        candles = market_data.candles(normalized, requested_day, interval)
        return ChartResponse(
            ticker=normalized,
            date=requested_day,
            interval=interval,
            data_mode="demo",
            candles=[
                CandleResponse(
                    timestamp_utc=candle.timestamp_utc,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                )
                for candle in candles
            ],
        )

    return app
