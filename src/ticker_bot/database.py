from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Self

import aiosqlite

from ticker_bot.criteria import ScannerCriteria


@dataclass(frozen=True, slots=True)
class TickerSummary:
    ticker: str
    mentions: int
    first_seen_utc: datetime
    last_seen_utc: datetime


@dataclass(frozen=True, slots=True)
class DayStats:
    unique_tickers: int
    total_mentions: int


@dataclass(frozen=True, slots=True)
class TickerReview:
    local_date: date
    ticker: str
    rating: int | None
    notes: str
    updated_at_utc: datetime


class TickerDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA busy_timeout = 5000")
        await connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            await connection.close()

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as connection:
            await connection.execute("PRAGMA journal_mode = WAL")
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ticker_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    chat_title TEXT,
                    message_id INTEGER NOT NULL,
                    ticker TEXT NOT NULL,
                    observed_at_utc TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    source TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    UNIQUE(chat_id, message_id, ticker)
                );

                CREATE INDEX IF NOT EXISTS idx_mentions_date_chat_ticker
                    ON ticker_mentions(local_date, chat_id, ticker);
                CREATE INDEX IF NOT EXISTS idx_mentions_observed
                    ON ticker_mentions(observed_at_utc);

                CREATE TABLE IF NOT EXISTS scanner_reviews (
                    local_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
                    notes TEXT NOT NULL DEFAULT '',
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(local_date, ticker)
                );

                CREATE TABLE IF NOT EXISTS scanner_criteria (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    min_price REAL,
                    max_price REAL,
                    min_change_percent REAL,
                    min_volume INTEGER,
                    min_relative_volume REAL,
                    max_float_millions REAL,
                    updated_at_utc TEXT NOT NULL
                );
                """
            )
            await connection.commit()

    async def replace_message_mentions(
        self,
        *,
        chat_id: int,
        chat_title: str | None,
        message_id: int,
        tickers: list[str],
        observed_at_utc: datetime,
        local_date: date,
        source: str,
    ) -> int:
        if observed_at_utc.tzinfo is None:
            raise ValueError("observed_at_utc must be timezone-aware")

        unique_tickers = list(dict.fromkeys(tickers))
        observed = observed_at_utc.astimezone(UTC).isoformat()
        recorded = datetime.now(UTC).isoformat()

        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute(
                "DELETE FROM ticker_mentions WHERE chat_id = ? AND message_id = ?",
                (chat_id, message_id),
            )
            await connection.executemany(
                """
                INSERT INTO ticker_mentions (
                    chat_id, chat_title, message_id, ticker, observed_at_utc,
                    local_date, source, recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chat_id,
                        chat_title,
                        message_id,
                        ticker,
                        observed,
                        local_date.isoformat(),
                        source,
                        recorded,
                    )
                    for ticker in unique_tickers
                ],
            )
            await connection.commit()
        return len(unique_tickers)

    async def list_tickers(
        self,
        *,
        local_date: date,
        chat_id: int | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[TickerSummary]:
        where = "local_date = ?"
        params: list[object] = [local_date.isoformat()]
        if chat_id is not None:
            where += " AND chat_id = ?"
            params.append(chat_id)
        params.extend([limit, offset])

        async with self._connect() as connection:
            cursor = await connection.execute(
                f"""
                SELECT ticker, COUNT(*) AS mentions,
                       MIN(observed_at_utc) AS first_seen_utc,
                       MAX(observed_at_utc) AS last_seen_utc
                FROM ticker_mentions
                WHERE {where}
                GROUP BY ticker
                ORDER BY first_seen_utc ASC, ticker ASC
                LIMIT ? OFFSET ?
                """,  # noqa: S608 - where contains only a fixed clause selected above.
                params,
            )
            rows = await cursor.fetchall()

        return [
            TickerSummary(
                ticker=row["ticker"],
                mentions=row["mentions"],
                first_seen_utc=datetime.fromisoformat(row["first_seen_utc"]),
                last_seen_utc=datetime.fromisoformat(row["last_seen_utc"]),
            )
            for row in rows
        ]

    async def day_stats(self, *, local_date: date, chat_id: int | None = None) -> DayStats:
        where = "local_date = ?"
        params: list[object] = [local_date.isoformat()]
        if chat_id is not None:
            where += " AND chat_id = ?"
            params.append(chat_id)

        async with self._connect() as connection:
            cursor = await connection.execute(
                f"""
                SELECT COUNT(DISTINCT ticker) AS unique_tickers,
                       COUNT(*) AS total_mentions
                FROM ticker_mentions
                WHERE {where}
                """,  # noqa: S608 - where contains only a fixed clause selected above.
                params,
            )
            row = await cursor.fetchone()

        return DayStats(
            unique_tickers=int(row["unique_tickers"]),
            total_mentions=int(row["total_mentions"]),
        )

    async def get_review(self, *, local_date: date, ticker: str) -> TickerReview | None:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT local_date, ticker, rating, notes, updated_at_utc
                FROM scanner_reviews
                WHERE local_date = ? AND ticker = ?
                """,
                (local_date.isoformat(), ticker.upper()),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return TickerReview(
            local_date=date.fromisoformat(row["local_date"]),
            ticker=row["ticker"],
            rating=row["rating"],
            notes=row["notes"],
            updated_at_utc=datetime.fromisoformat(row["updated_at_utc"]),
        )

    async def save_review(
        self,
        *,
        local_date: date,
        ticker: str,
        rating: int | None,
        notes: str,
    ) -> TickerReview:
        if rating is not None and not 1 <= rating <= 5:
            raise ValueError("rating must be between 1 and 5")
        updated_at = datetime.now(UTC)
        normalized_ticker = ticker.upper()
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO scanner_reviews (
                    local_date, ticker, rating, notes, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(local_date, ticker) DO UPDATE SET
                    rating = excluded.rating,
                    notes = excluded.notes,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    local_date.isoformat(),
                    normalized_ticker,
                    rating,
                    notes,
                    updated_at.isoformat(),
                ),
            )
            await connection.commit()
        return TickerReview(
            local_date=local_date,
            ticker=normalized_ticker,
            rating=rating,
            notes=notes,
            updated_at_utc=updated_at,
        )

    async def get_criteria(self) -> ScannerCriteria:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT min_price, max_price, min_change_percent, min_volume,
                       min_relative_volume, max_float_millions
                FROM scanner_criteria
                WHERE id = 1
                """
            )
            row = await cursor.fetchone()
        if row is None:
            return ScannerCriteria()
        return ScannerCriteria(
            min_price=row["min_price"],
            max_price=row["max_price"],
            min_change_percent=row["min_change_percent"],
            min_volume=row["min_volume"],
            min_relative_volume=row["min_relative_volume"],
            max_float_millions=row["max_float_millions"],
        )

    async def save_criteria(self, criteria: ScannerCriteria) -> ScannerCriteria:
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO scanner_criteria (
                    id, min_price, max_price, min_change_percent, min_volume,
                    min_relative_volume, max_float_millions, updated_at_utc
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    min_price = excluded.min_price,
                    max_price = excluded.max_price,
                    min_change_percent = excluded.min_change_percent,
                    min_volume = excluded.min_volume,
                    min_relative_volume = excluded.min_relative_volume,
                    max_float_millions = excluded.max_float_millions,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    criteria.min_price,
                    criteria.max_price,
                    criteria.min_change_percent,
                    criteria.min_volume,
                    criteria.min_relative_volume,
                    criteria.max_float_millions,
                    datetime.now(UTC).isoformat(),
                ),
            )
            await connection.commit()
        return criteria

    async def check(self) -> bool:
        try:
            async with self._connect() as connection:
                cursor = await connection.execute("SELECT 1")
                row = await cursor.fetchone()
                return row is not None and row[0] == 1
        except aiosqlite.Error:
            return False

    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    async def __aexit__(self, *_: object) -> None:
        return None
