from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn
from dotenv import load_dotenv

from ticker_bot.api import create_app
from ticker_bot.config import ConfigurationError, Settings


def _open_browser_when_ready(port: int) -> None:
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{url}/healthz", timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.5)


def run(*, open_browser: bool = False) -> None:
    load_dotenv()
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        raise SystemExit(f"Помилка конфігурації: {exc}") from exc

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # HTTP client INFO logs include full request URLs. Telegram authentication
    # belongs in those URLs, so keep them out of normal application logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if open_browser:
        threading.Thread(
            target=_open_browser_when_ready,
            args=(settings.api_port,),
            daemon=True,
        ).start()
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    run()


if __name__ == "__main__":
    main()
