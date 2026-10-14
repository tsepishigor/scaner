from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from ticker_bot.criteria import ScannerCriteria
from ticker_bot.database import TickerDatabase
from ticker_bot.extractor import TickerExtractor
from ticker_bot.ingestion import TickerIngestionService


@pytest.fixture
async def database(tmp_path):
    instance = TickerDatabase(tmp_path / "tickers.db")
    await instance.initialize()
    return instance


@pytest.fixture
def ingestion(database):
    return TickerIngestionService(
        database=database,
        extractor=TickerExtractor(),
        timezone_=ZoneInfo("Europe/Kyiv"),
    )


async def test_ingestion_uses_kyiv_day_and_counts_once_per_message(database, ingestion) -> None:
    # 22:30 UTC is already the next calendar day in Kyiv in October.
    observed = datetime(2026, 10, 11, 22, 30, tzinfo=UTC)
    result = await ingestion.ingest(
        chat_id=-100123,
        chat_title="Trading",
        message_id=10,
        text="AAPL AAPL and $nvda",
        observed_at=observed,
        source="supergroup",
    )
    await ingestion.ingest(
        chat_id=-100123,
        chat_title="Trading",
        message_id=11,
        text="$AAPL",
        observed_at=observed,
        source="supergroup",
    )

    assert result.tickers == ("AAPL", "NVDA")
    assert result.local_date == "2026-10-12"
    rows = await database.list_tickers(local_date=date(2026, 10, 12), chat_id=-100123)
    assert [(row.ticker, row.mentions) for row in rows] == [("AAPL", 2), ("NVDA", 1)]


async def test_replayed_and_edited_message_is_reconciled(database, ingestion) -> None:
    observed = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
    arguments = {
        "chat_id": -100123,
        "chat_title": "Trading",
        "message_id": 55,
        "observed_at": observed,
        "source": "channel",
    }
    await ingestion.ingest(text="AAPL NVDA", **arguments)
    await ingestion.ingest(text="AAPL NVDA", **arguments)

    stats = await database.day_stats(local_date=date(2026, 10, 12), chat_id=-100123)
    assert stats.unique_tickers == 2
    assert stats.total_mentions == 2

    await ingestion.ingest(text="MSFT", **arguments)
    rows = await database.list_tickers(local_date=date(2026, 10, 12), chat_id=-100123)
    assert [(row.ticker, row.mentions) for row in rows] == [("MSFT", 1)]


async def test_command_reconciliation_removes_old_mentions(database, ingestion) -> None:
    observed = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
    arguments = {
        "chat_id": -100123,
        "chat_title": "Trading",
        "message_id": 99,
        "observed_at": observed,
        "source": "supergroup",
    }
    await ingestion.ingest(text="AAPL", **arguments)
    await ingestion.ingest(text="/today AAPL", is_command=True, **arguments)

    stats = await database.day_stats(local_date=date(2026, 10, 12), chat_id=-100123)
    assert stats.total_mentions == 0


async def test_chat_filter_keeps_results_separate(database, ingestion) -> None:
    observed = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
    for chat_id in (-1001, -1002):
        await ingestion.ingest(
            chat_id=chat_id,
            chat_title=None,
            message_id=1,
            text="AAPL",
            observed_at=observed,
            source="channel",
        )

    stats_all = await database.day_stats(local_date=date(2026, 10, 12))
    stats_one = await database.day_stats(local_date=date(2026, 10, 12), chat_id=-1001)
    assert stats_all.total_mentions == 2
    assert stats_all.unique_tickers == 1
    assert stats_one.total_mentions == 1


async def test_scanner_settings_and_review_are_persisted(database) -> None:
    criteria = ScannerCriteria(
        min_price=3.5,
        min_volume=1_000_000,
        min_relative_volume=2.0,
    )
    await database.save_criteria(criteria)
    review = await database.save_review(
        local_date=date(2026, 10, 12),
        ticker="aapl",
        rating=5,
        notes="Сильний сетап",
    )

    assert await database.get_criteria() == criteria
    assert review.ticker == "AAPL"
    loaded = await database.get_review(local_date=date(2026, 10, 12), ticker="AAPL")
    assert loaded is not None
    assert loaded.rating == 5
    assert loaded.notes == "Сильний сетап"
