from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ticker_bot.database import TickerDatabase
from ticker_bot.extractor import TickerExtractor


@dataclass(frozen=True, slots=True)
class IngestionResult:
    tickers: tuple[str, ...]
    local_date: str


class TickerIngestionService:
    def __init__(
        self,
        *,
        database: TickerDatabase,
        extractor: TickerExtractor,
        timezone_: ZoneInfo,
    ) -> None:
        self.database = database
        self.extractor = extractor
        self.timezone = timezone_

    async def ingest(
        self,
        *,
        chat_id: int,
        chat_title: str | None,
        message_id: int,
        text: str | None,
        observed_at: datetime,
        source: str,
        is_command: bool = False,
    ) -> IngestionResult:
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        observed_at_utc = observed_at.astimezone(UTC)
        local_day = observed_at_utc.astimezone(self.timezone).date()
        tickers = [] if is_command else self.extractor.extract(text)

        await self.database.replace_message_mentions(
            chat_id=chat_id,
            chat_title=chat_title,
            message_id=message_id,
            tickers=tickers,
            observed_at_utc=observed_at_utc,
            local_date=local_day,
            source=source,
        )
        return IngestionResult(tickers=tuple(tickers), local_date=local_day.isoformat())
