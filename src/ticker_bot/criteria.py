from __future__ import annotations

from dataclasses import dataclass

from ticker_bot.market_data import MarketSnapshot


@dataclass(frozen=True, slots=True)
class ScannerCriteria:
    min_price: float | None = None
    max_price: float | None = None
    min_change_percent: float | None = None
    min_volume: int | None = None
    min_relative_volume: float | None = None
    max_float_millions: float | None = None

    @property
    def active_count(self) -> int:
        return sum(
            value is not None
            for value in (
                self.min_price,
                self.max_price,
                self.min_change_percent,
                self.min_volume,
                self.min_relative_volume,
                self.max_float_millions,
            )
        )


@dataclass(frozen=True, slots=True)
class CriteriaResult:
    matches: bool
    failed_rules: tuple[str, ...]


def evaluate_criteria(
    snapshot: MarketSnapshot,
    criteria: ScannerCriteria,
) -> CriteriaResult:
    failed: list[str] = []
    if criteria.min_price is not None and snapshot.price < criteria.min_price:
        failed.append("min_price")
    if criteria.max_price is not None and snapshot.price > criteria.max_price:
        failed.append("max_price")
    if (
        criteria.min_change_percent is not None
        and snapshot.change_percent < criteria.min_change_percent
    ):
        failed.append("min_change_percent")
    if criteria.min_volume is not None and snapshot.volume < criteria.min_volume:
        failed.append("min_volume")
    if (
        criteria.min_relative_volume is not None
        and snapshot.relative_volume < criteria.min_relative_volume
    ):
        failed.append("min_relative_volume")
    if (
        criteria.max_float_millions is not None
        and snapshot.float_millions > criteria.max_float_millions
    ):
        failed.append("max_float_millions")
    return CriteriaResult(matches=not failed, failed_rules=tuple(failed))
