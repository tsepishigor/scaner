from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from telegram import Bot, Update

from ticker_bot.config import Settings
from ticker_bot.database import TickerDatabase
from ticker_bot.extractor import TickerExtractor
from ticker_bot.ingestion import TickerIngestionService
from ticker_bot.telegram_bot import TelegramBotService


def make_service(tmp_path, allowed_chat_ids: frozenset[int]):
    database = TickerDatabase(tmp_path / "telegram.db")
    settings = Settings(
        telegram_bot_token="123:TEST",
        bot_enabled=True,
        allowed_chat_ids=allowed_chat_ids,
        app_timezone=ZoneInfo("Europe/Kyiv"),
        database_path=database.path,
        enable_plain_tickers=True,
        api_host="127.0.0.1",
        api_port=8000,
        scanner_api_token=None,
        scanner_site_password=None,
        log_level="INFO",
    )
    ingestion = TickerIngestionService(
        database=database,
        extractor=TickerExtractor(),
        timezone_=settings.app_timezone,
    )
    return database, TelegramBotService(
        settings=settings,
        database=database,
        ingestion=ingestion,
    )


async def test_channel_caption_is_ingested_and_unauthorized_chat_is_ignored(tmp_path) -> None:
    allowed_chat_id = -1001234567890
    database, service = make_service(tmp_path, frozenset({allowed_chat_id}))
    await database.initialize()
    bot = Bot("123:TEST")
    timestamp = int(datetime(2026, 10, 12, 10, 0, tzinfo=UTC).timestamp())

    update = Update.de_json(
        {
            "update_id": 1,
            "channel_post": {
                "message_id": 7,
                "date": timestamp,
                "chat": {
                    "id": allowed_chat_id,
                    "type": "channel",
                    "title": "Trading channel",
                },
                "document": {
                    "file_id": "file-id",
                    "file_unique_id": "unique-id",
                    "file_name": "chart.png",
                },
                "caption": "$aapl NVDA",
            },
        },
        bot,
    )
    await service._capture_message(update, None)  # type: ignore[arg-type]

    ignored_update = Update.de_json(
        {
            "update_id": 2,
            "message": {
                "message_id": 8,
                "date": timestamp,
                "chat": {"id": -100999, "type": "supergroup", "title": "Other"},
                "text": "MSFT",
            },
        },
        bot,
    )
    await service._capture_message(ignored_update, None)  # type: ignore[arg-type]

    rows = await database.list_tickers(
        local_date=date(2026, 10, 12),
        chat_id=allowed_chat_id,
    )
    assert [(row.ticker, row.mentions) for row in rows] == [("AAPL", 1), ("NVDA", 1)]
    ignored_stats = await database.day_stats(local_date=date(2026, 10, 12), chat_id=-100999)
    assert ignored_stats.unique_tickers == 0
    assert ignored_stats.total_mentions == 0
