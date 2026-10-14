from ticker_bot.extractor import TickerExtractor


def test_extracts_supported_ticker_formats_in_message_order() -> None:
    extractor = TickerExtractor()

    result = extractor.extract("Ідеї: $aapl, потім NVDA; NASDAQ:tsla та BRK-B. BUY AAPL AAPL")

    assert result == ["AAPL", "NVDA", "TSLA", "BRK.B"]


def test_explicit_ticker_bypasses_plain_word_stoplist() -> None:
    extractor = TickerExtractor()

    assert extractor.extract("AI BUY $AI $buy") == ["AI", "BUY"]


def test_ignores_urls_emails_mentions_and_common_uppercase_words() -> None:
    extractor = TickerExtractor()

    result = extractor.extract("NEWS https://example.com/AAPL test@NVDA.com @TSLA BUY THIS ETF")

    assert result == []


def test_can_require_explicit_ticker_syntax() -> None:
    extractor = TickerExtractor(include_plain=False)

    assert extractor.extract("AAPL $nvda NYSE:brk.b") == ["NVDA", "BRK.B"]


def test_none_and_empty_text_have_no_tickers() -> None:
    extractor = TickerExtractor()

    assert extractor.extract(None) == []
    assert extractor.extract("") == []
