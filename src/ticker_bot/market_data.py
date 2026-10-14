from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    ticker: str
    price: float
    change_percent: float
    volume: int
    relative_volume: float
    float_millions: float
    market_cap_millions: float
    previous_close: float
    source: str = "demo"


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class DemoMarketDataProvider:
    """Stable synthetic data used only until a Polygon key is connected."""

    _interval_minutes = {"1": 1, "2": 2, "5": 5, "15": 15, "60": 60}

    @staticmethod
    def _seed(ticker: str, selected_day: date, suffix: str) -> int:
        digest = hashlib.sha256(
            f"{ticker.upper()}:{selected_day.isoformat()}:{suffix}".encode()
        ).digest()
        return int.from_bytes(digest[:8], "big")

    def snapshot(self, ticker: str, selected_day: date) -> MarketSnapshot:
        ticker = ticker.upper()
        rng = random.Random(self._seed(ticker, selected_day, "snapshot"))
        previous_close = round(4 + rng.random() * 196, 2)
        change_percent = round(-8 + rng.random() * 24, 2)
        price = round(max(0.5, previous_close * (1 + change_percent / 100)), 2)
        float_millions = round(3 + rng.random() * 297, 1)
        return MarketSnapshot(
            ticker=ticker,
            price=price,
            change_percent=change_percent,
            volume=int(150_000 + rng.random() * 14_850_000),
            relative_volume=round(0.35 + rng.random() * 5.65, 2),
            float_millions=float_millions,
            market_cap_millions=round(price * float_millions * (1.05 + rng.random()), 1),
            previous_close=previous_close,
        )

    def candles(self, ticker: str, selected_day: date, interval: str) -> list[Candle]:
        if interval == "1D":
            return self._daily_candles(ticker, selected_day)
        if interval not in self._interval_minutes:
            raise ValueError("Unsupported interval")

        minutes = self._interval_minutes[interval]
        points = (6 * 60 + 30) // minutes
        market_timezone = ZoneInfo("America/New_York")
        start = datetime.combine(selected_day, time(9, 30), tzinfo=market_timezone)
        snapshot = self.snapshot(ticker, selected_day)
        rng = random.Random(self._seed(ticker, selected_day, f"candles-{interval}"))
        open_price = snapshot.previous_close * (1 + rng.uniform(-0.025, 0.04))
        current = open_price
        result: list[Candle] = []

        for index in range(points):
            progress = (index + 1) / points
            target = open_price + (snapshot.price - open_price) * progress
            volatility = max(0.0025, 0.012 / (minutes**0.35))
            candle_open = current
            candle_close = max(
                0.25,
                candle_open
                + (target - candle_open) * 0.16
                + candle_open * rng.gauss(0, volatility),
            )
            wick = candle_open * abs(rng.gauss(volatility * 0.7, volatility * 0.35))
            high = max(candle_open, candle_close) + wick
            low = max(0.1, min(candle_open, candle_close) - wick * rng.uniform(0.65, 1.15))
            volume_weight = 1.7 if index < points * 0.12 or index > points * 0.82 else 0.75
            candle_volume = int(snapshot.volume / points * volume_weight * rng.uniform(0.55, 1.45))
            result.append(
                Candle(
                    timestamp_utc=(start + timedelta(minutes=index * minutes)).astimezone(UTC),
                    open=round(candle_open, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(candle_close, 2),
                    volume=max(1, candle_volume),
                )
            )
            current = candle_close

        return result

    def _daily_candles(self, ticker: str, selected_day: date) -> list[Candle]:
        market_timezone = ZoneInfo("America/New_York")
        days: list[date] = []
        cursor = selected_day
        while len(days) < 40:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor -= timedelta(days=1)
        days.reverse()

        snapshot = self.snapshot(ticker, selected_day)
        rng = random.Random(self._seed(ticker, selected_day, "daily-candles"))
        current = snapshot.previous_close * rng.uniform(0.72, 1.08)
        result: list[Candle] = []
        for index, candle_day in enumerate(days):
            progress = (index + 1) / len(days)
            target = current + (snapshot.price - current) * max(0.04, progress * 0.12)
            candle_open = current * (1 + rng.gauss(0, 0.012))
            candle_close = max(0.25, target * (1 + rng.gauss(0, 0.018)))
            wick = max(candle_open, candle_close) * abs(rng.gauss(0.012, 0.005))
            result.append(
                Candle(
                    timestamp_utc=datetime.combine(
                        candle_day,
                        time(16, 0),
                        tzinfo=market_timezone,
                    ).astimezone(UTC),
                    open=round(candle_open, 2),
                    high=round(max(candle_open, candle_close) + wick, 2),
                    low=round(max(0.1, min(candle_open, candle_close) - wick), 2),
                    close=round(candle_close, 2),
                    volume=int(snapshot.volume * rng.uniform(0.45, 1.5)),
                )
            )
            current = candle_close
        return result
