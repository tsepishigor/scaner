from __future__ import annotations

import re

DEFAULT_STOPWORDS = frozenset(
    {
        "A",
        "AI",
        "AM",
        "AND",
        "ATH",
        "BUY",
        "CALL",
        "CEO",
        "CFO",
        "CLOSE",
        "DAY",
        "ETF",
        "FOR",
        "FROM",
        "GAP",
        "HIGH",
        "HTTP",
        "HTTPS",
        "IPO",
        "LONG",
        "LOW",
        "NEWS",
        "NYSE",
        "NASDAQ",
        "NOW",
        "OPEN",
        "OTC",
        "PM",
        "PUT",
        "SEC",
        "SELL",
        "SHORT",
        "SL",
        "THE",
        "THIS",
        "TODAY",
        "TP",
        "USA",
        "USD",
        "VWAP",
        "WATCH",
        "WEEK",
        "WITH",
    }
)

_TICKER_BODY = r"[A-Za-z]{1,6}(?:[.-][A-Za-z]{1,2})?"
_EXPLICIT_RE = re.compile(rf"(?<![\w$#])[$#]({_TICKER_BODY})(?![A-Za-z0-9_-])")
_EXCHANGE_RE = re.compile(
    rf"\b(?:NASDAQ|NYSE|AMEX|ARCA|OTC)\s*:\s*({_TICKER_BODY})(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
_PLAIN_RE = re.compile(r"(?<![A-Za-z0-9@/#$])([A-Z]{1,6}(?:[.-][A-Z]{1,2})?)(?![A-Za-z0-9-])")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL_OR_MENTION_RE = re.compile(r"(?:\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|@[A-Za-z0-9_]{3,})")


def _normalize(candidate: str) -> str:
    return candidate.upper().replace("-", ".")


class TickerExtractor:
    def __init__(
        self,
        *,
        include_plain: bool = True,
        stopwords: frozenset[str] = DEFAULT_STOPWORDS,
    ) -> None:
        self.include_plain = include_plain
        self.stopwords = stopwords

    def extract(self, text: str | None) -> list[str]:
        if not text:
            return []

        sanitized = _EMAIL_OR_MENTION_RE.sub(" ", _URL_RE.sub(" ", text))
        positioned: list[tuple[int, str]] = []
        positioned.extend(
            (match.start(1), _normalize(match.group(1)))
            for match in _EXPLICIT_RE.finditer(sanitized)
        )
        positioned.extend(
            (match.start(1), _normalize(match.group(1)))
            for match in _EXCHANGE_RE.finditer(sanitized)
        )
        if self.include_plain:
            for match in _PLAIN_RE.finditer(sanitized):
                ticker = _normalize(match.group(1))
                if ticker not in self.stopwords:
                    positioned.append((match.start(1), ticker))

        # Preserve message order while storing at most one mention per ticker/message.
        candidates = [ticker for _, ticker in sorted(positioned, key=lambda item: item[0])]
        return list(dict.fromkeys(candidates))
