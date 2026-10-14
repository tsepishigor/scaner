from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, date, datetime
from typing import Any

from telegram import BotCommand, InputFile, MessageEntity, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from ticker_bot.config import Settings
from ticker_bot.database import TickerDatabase
from ticker_bot.ingestion import TickerIngestionService

logger = logging.getLogger(__name__)


class TelegramBotService:
    def __init__(
        self,
        *,
        settings: Settings,
        database: TickerDatabase,
        ingestion: TickerIngestionService,
    ) -> None:
        if not settings.telegram_bot_token:
            raise ValueError("Telegram token is required when the bot is enabled")
        self.settings = settings
        self.database = database
        self.ingestion = ingestion
        self.application: Application[Any, Any, Any, Any, Any, Any] | None = None
        self.running = False

    def _build_application(self) -> Application[Any, Any, Any, Any, Any, Any]:
        application = Application.builder().token(self.settings.telegram_bot_token).build()
        application.add_handler(CommandHandler("start", self._help_command), group=0)
        application.add_handler(CommandHandler("help", self._help_command), group=0)
        application.add_handler(CommandHandler("chatid", self._chat_id_command), group=0)
        application.add_handler(CommandHandler("today", self._today_command), group=0)
        application.add_handler(CommandHandler("stats", self._stats_command), group=0)
        application.add_handler(CommandHandler("export", self._export_command), group=0)
        # A separate group lets commands respond while still reconciling edited messages.
        application.add_handler(MessageHandler(filters.ALL, self._capture_message), group=1)
        application.add_error_handler(self._error_handler)
        return application

    async def start(self) -> None:
        if self.running:
            return
        self.application = self._build_application()
        try:
            await self.application.initialize()
            await self.application.bot.set_my_commands(
                [
                    BotCommand("today", "Тікери за сьогодні"),
                    BotCommand("stats", "Коротка статистика за сьогодні"),
                    BotCommand("export", "Завантажити CSV за сьогодні"),
                    BotCommand("chatid", "Показати ID цього чату"),
                    BotCommand("help", "Допомога"),
                ]
            )
            if self.application.updater is None:
                raise RuntimeError("Telegram updater is unavailable")
            await self.application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=False,
            )
            await self.application.start()
            self.running = True
            logger.info("Telegram bot polling started")
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        if self.application is None:
            return
        try:
            if self.application.updater is not None and self.application.updater.running:
                await self.application.updater.stop()
            if self.application.running:
                await self.application.stop()
            await self.application.shutdown()
        finally:
            self.running = False
            logger.info("Telegram bot stopped")

    async def _capture_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        chat = update.effective_chat
        if message is None or chat is None or not self.settings.chat_is_allowed(chat.id):
            return

        text = message.text if message.text is not None else message.caption
        entities = message.entities if message.text is not None else message.caption_entities
        is_command = any(
            entity.type == MessageEntity.BOT_COMMAND and entity.offset == 0
            for entity in (entities or ())
        )
        result = await self.ingestion.ingest(
            chat_id=chat.id,
            chat_title=chat.title,
            message_id=message.message_id,
            text=text,
            observed_at=message.date,
            source=str(chat.type),
            is_command=is_command,
        )
        if result.tickers:
            logger.info(
                "Stored %d unique ticker(s) from chat_id=%d message_id=%d",
                len(result.tickers),
                chat.id,
                message.message_id,
            )

    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        if message is None:
            return
        await message.reply_text(
            "Я збираю тікери з нових повідомлень без зайвих відповідей у чат.\n\n"
            "Приклади: AAPL, $NVDA, NASDAQ:TSLA, BRK.B\n\n"
            "/today — список за сьогодні\n"
            "/stats — коротка статистика\n"
            "/export — CSV-файл за сьогодні\n"
            "/chatid — ID поточного чату\n"
            "/help — ця підказка"
        )

    async def _chat_id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        chat = update.effective_chat
        if message is not None and chat is not None:
            await message.reply_text(f"ID цього чату: {chat.id}")

    async def _require_allowed_chat(self, update: Update) -> bool:
        message = update.effective_message
        chat = update.effective_chat
        if message is None or chat is None:
            return False
        if self.settings.chat_is_allowed(chat.id):
            return True
        await message.reply_text(
            "Цей чат не входить до ALLOWED_CHAT_IDS. Команда /chatid покаже його ID."
        )
        return False

    def _today(self) -> date:
        return datetime.now(UTC).astimezone(self.settings.app_timezone).date()

    async def _today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_allowed_chat(update):
            return
        message = update.effective_message
        chat = update.effective_chat
        assert message is not None and chat is not None

        day = self._today()
        stats = await self.database.day_stats(local_date=day, chat_id=chat.id)
        rows = await self.database.list_tickers(local_date=day, chat_id=chat.id, limit=100)
        if not rows:
            await message.reply_text(f"За {day.isoformat()} тікерів ще немає.")
            return

        lines = [
            f"Тікери за {day.isoformat()}: {stats.unique_tickers} унікальних, "
            f"{stats.total_mentions} згадок."
        ]
        lines.extend(
            f"{index}. {row.ticker} — {row.mentions}" for index, row in enumerate(rows, start=1)
        )
        if stats.unique_tickers > len(rows):
            lines.append("Повний список: /export")
        await message.reply_text("\n".join(lines))

    async def _stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_allowed_chat(update):
            return
        message = update.effective_message
        chat = update.effective_chat
        assert message is not None and chat is not None

        day = self._today()
        stats = await self.database.day_stats(local_date=day, chat_id=chat.id)
        await message.reply_text(
            f"{day.isoformat()}: {stats.unique_tickers} унікальних тікерів, "
            f"{stats.total_mentions} згадок."
        )

    async def _export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_allowed_chat(update):
            return
        message = update.effective_message
        chat = update.effective_chat
        assert message is not None and chat is not None

        day = self._today()
        rows = []
        page_size = 500
        while True:
            page = await self.database.list_tickers(
                local_date=day,
                chat_id=chat.id,
                limit=page_size,
                offset=len(rows),
            )
            rows.extend(page)
            if len(page) < page_size:
                break
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["ticker", "mentions", "first_seen_utc", "last_seen_utc"])
        for row in rows:
            writer.writerow(
                [
                    row.ticker,
                    row.mentions,
                    row.first_seen_utc.isoformat(),
                    row.last_seen_utc.isoformat(),
                ]
            )
        payload = io.BytesIO(output.getvalue().encode("utf-8-sig"))
        await message.reply_document(
            document=InputFile(payload, filename=f"tickers-{day.isoformat()}.csv"),
            caption=f"Тікери за {day.isoformat()}: {len(rows)} унікальних.",
        )

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        update_id = update.update_id if isinstance(update, Update) else None
        logger.error(
            "Telegram update failed: update_id=%s error_type=%s",
            update_id,
            type(context.error).__name__,
        )
