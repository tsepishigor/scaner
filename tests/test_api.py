import asyncio
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from ticker_bot.api import create_app
from ticker_bot.config import Settings
from ticker_bot.database import TickerDatabase


def make_settings(tmp_path, *, api_token=None, site_password=None) -> Settings:
    return Settings(
        telegram_bot_token=None,
        bot_enabled=False,
        allowed_chat_ids=frozenset(),
        app_timezone=ZoneInfo("Europe/Kyiv"),
        database_path=tmp_path / "tickers.db",
        enable_plain_tickers=True,
        api_host="127.0.0.1",
        api_port=8000,
        scanner_api_token=api_token,
        scanner_site_password=site_password,
        log_level="INFO",
    )


def seed_database(path) -> None:
    async def seed() -> None:
        database = TickerDatabase(path)
        await database.initialize()
        await database.replace_message_mentions(
            chat_id=-100123,
            chat_title="Trading",
            message_id=7,
            tickers=["AAPL", "NVDA"],
            observed_at_utc=datetime(2026, 10, 12, 10, 0, tzinfo=UTC),
            local_date=date(2026, 10, 12),
            source="supergroup",
        )

    asyncio.run(seed())


def test_health_readiness_and_ticker_api(tmp_path) -> None:
    settings = make_settings(tmp_path)
    seed_database(settings.database_path)

    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        assert client.get("/readyz").json() == {"status": "ready"}
        response = client.get("/api/v1/tickers", params={"day": "2026-10-12", "chat_id": -100123})

    assert response.status_code == 200
    body = response.json()
    assert body["unique_tickers"] == 2
    assert body["total_mentions"] == 2
    assert [item["ticker"] for item in body["items"]] == ["AAPL", "NVDA"]


def test_api_bearer_token_is_enforced(tmp_path) -> None:
    settings = make_settings(tmp_path, api_token="correct-secret")

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/tickers").status_code == 401
        assert (
            client.get(
                "/api/v1/tickers",
                headers={"Authorization": "Bearer wrong-secret"},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/v1/tickers",
                headers={"Authorization": "Bearer correct-secret"},
            ).status_code
            == 200
        )


def test_api_rejects_invalid_date_and_limit(tmp_path) -> None:
    settings = make_settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/tickers", params={"day": "not-a-date"}).status_code == 422
        assert client.get("/api/v1/tickers", params={"limit": 501}).status_code == 422


def test_scanner_page_and_preview_data(tmp_path) -> None:
    settings = make_settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        page = client.get("/")
        scanner = client.get(
            "/api/v1/scanner",
            params={"day": "2026-10-12", "preview_if_empty": True},
        )
        chart = client.get(
            "/api/v1/scanner/chart/AAPL",
            params={"day": "2026-10-12", "interval": "5"},
        )

    assert page.status_code == 200
    assert "Огляд тікерів" in page.text
    assert scanner.status_code == 200
    assert scanner.json()["preview"] is True
    assert scanner.json()["data_mode"] == "demo"
    assert scanner.json()["total_count"] == 5
    assert chart.status_code == 200
    assert chart.json()["ticker"] == "AAPL"
    assert len(chart.json()["candles"]) == 78


def test_scanner_criteria_and_review_round_trip(tmp_path) -> None:
    settings = make_settings(tmp_path)
    seed_database(settings.database_path)

    with TestClient(create_app(settings)) as client:
        criteria = client.put(
            "/api/v1/scanner/criteria",
            json={"min_price": 10, "min_volume": 100_000},
        )
        scanner = client.get("/api/v1/scanner", params={"day": "2026-10-12"})
        review = client.put(
            "/api/v1/scanner/reviews/AAPL",
            params={"day": "2026-10-12"},
            json={"rating": 4, "notes": "Гарна точка входу"},
        )
        scanner_after_review = client.get(
            "/api/v1/scanner",
            params={"day": "2026-10-12"},
        )

    assert criteria.status_code == 200
    assert criteria.json()["min_price"] == 10
    assert scanner.json()["active_criteria"] == 2
    assert review.status_code == 200
    assert review.json()["rating"] == 4
    aapl = next(item for item in scanner_after_review.json()["items"] if item["ticker"] == "AAPL")
    assert aapl["rating"] == 4
    assert aapl["notes"] == "Гарна точка входу"


def test_manual_ticker_can_be_added_for_selected_day(tmp_path) -> None:
    settings = make_settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        added = client.post(
            "/api/v1/tickers/manual",
            json={"ticker": "nvda", "day": "2026-10-12"},
        )
        scanner = client.get("/api/v1/scanner", params={"day": "2026-10-12"})

    assert added.status_code == 200
    assert added.json()["ticker"] == "NVDA"
    assert [item["ticker"] for item in scanner.json()["items"]] == ["NVDA"]


def test_scanner_validates_criteria_and_ticker(tmp_path) -> None:
    settings = make_settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        invalid_range = client.put(
            "/api/v1/scanner/criteria",
            json={"min_price": 20, "max_price": 10},
        )
        invalid_ticker = client.get("/api/v1/scanner/chart/not-a-ticker")

    assert invalid_range.status_code == 422
    assert invalid_ticker.status_code == 422


def test_site_password_protects_scanner_and_api(tmp_path) -> None:
    settings = make_settings(tmp_path, site_password="correct-password")

    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").status_code == 200
        redirect = client.get("/", follow_redirects=False)
        assert redirect.status_code == 303
        assert redirect.headers["location"] == "/login"
        assert client.get("/api/v1/scanner").status_code == 401
        assert client.post("/api/session/login", json={"password": "wrong"}).status_code == 401
        login = client.post(
            "/api/session/login",
            json={"password": "correct-password"},
        )
        assert login.status_code == 200
        assert client.get("/").status_code == 200


def test_site_login_authorizes_browser_when_api_token_is_also_set(tmp_path) -> None:
    settings = make_settings(
        tmp_path,
        api_token="api-secret",
        site_password="site-password",
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/scanner").status_code == 401
        assert (
            client.post(
                "/api/session/login",
                json={"password": "site-password"},
            ).status_code
            == 200
        )
        assert client.get("/api/v1/scanner").status_code == 200
